from django.contrib.auth import authenticate
from django.contrib.auth.models import User
import mimetypes
import threading
import re
from pathlib import Path

from django.db import close_old_connections, transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Courseware, QARecord, SlideContent, SummaryRecord
from .serializers import (
    CoursewareUploadSerializer,
    LoginSerializer,
    QARecordSerializer,
    QARequestSerializer,
    RegisterSerializer,
    SlideContentSerializer,
    SummaryRecordSerializer,
)
from .services.ppt_parser_service import PPTParserService
from .services.qa_service import QAService
from .services.slide_render_service import SlideRenderService
from .services.image_processing_service import ImageProcessingService
from .services.summary_service import SummaryService
from .services.translation_service import TranslationService
from .services.vector_index_service import VectorIndexService

from app.debug_logger import debug_log


# 实现 sync_courseware_title_from_file 对应的核心处理，封装输入转换、状态更新或结果返回。
def sync_courseware_title_from_file(courseware: Courseware) -> None:
    # Keep the upload-time title as source of truth (preserves original filename
    # and duplicate numbering like "(2)"), only backfill when title is empty.
    if str(courseware.title or "").strip():
        return
    file_name = Path(getattr(courseware.file, "name", "") or "").stem.strip()
    if file_name:
        courseware.title = file_name
        courseware.save(update_fields=["title", "updated_at"])


# 实现数据规范化和结构构建，让调用方获得稳定的输出。
def build_courseware_progress(courseware: Courseware) -> dict:
    # 进度统计不能只看 translated_text：无文字页本身不需要翻译，也应算作已处理，避免前端进度卡在最后几页。
    slides = list(courseware.slides.only("slide_no", "translation_done", "preview_done", "source_text", "source_layout"))
    total = len(slides)
    translated = 0
    for slide in slides:
        if slide.translation_done:
            translated += 1
            continue
        if str(slide.source_text or "").strip():
            continue
        source_layout = slide.source_layout or {}
        containers = source_layout.get("text_containers", []) or []
        has_text_container = any(
            str(item.get("kind", "")) != "image_ocr" and str(item.get("text", "")).strip()
            for item in containers
        )
        if not has_text_container:
            translated += 1
    rendered = sum(1 for slide in slides if slide.preview_done)
    return {
        "total_slides": total,
        "translated_slides": translated,
        "rendered_slides": rendered,
    }


# 实现数据规范化和结构构建，让调用方获得稳定的输出。
def build_translation_duration_seconds(courseware: Courseware) -> int | None:
    # 翻译中实时计算耗时，完成后优先使用落库值，保证刷新页面时展示一致。
    started_at = courseware.translation_started_at
    if not started_at:
        return courseware.translation_duration_seconds
    if courseware.status == Courseware.STATUS_TRANSLATING:
        return max(int((timezone.now() - started_at).total_seconds()), 0)
    if courseware.translation_duration_seconds is not None:
        return courseware.translation_duration_seconds
    return max(int((timezone.now() - started_at).total_seconds()), 0)


# 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
def build_translated_slides_data(slides: list[SlideContent]) -> list[dict]:
    # 导出服务只需要原图、源布局和译文布局，避免把整个 ORM 对象传进文件处理层造成隐式数据库访问。
    return [
        {
            "slide_no": slide.slide_no,
            "source_image_url": slide.source_image_url,
            "source_layout": slide.source_layout,
            "translated_layout": slide.translated_layout,
        }
        for slide in slides
        if slide.translated_layout
    ]


# 实现问答上下文构建和结果整理，保证回答与课件内容关联。
def run_post_translation_tasks(courseware_id: int, owner_id: int) -> None:
    # 翻译完成后的预览渲染和向量索引重建耗时较长，拆到独立后台任务，避免阻塞翻译接口响应。
    close_old_connections()
    try:
        courseware = Courseware.objects.get(id=courseware_id, owner_id=owner_id)
        slides = list(courseware.slides.order_by("slide_no", "id"))
        TranslationService().build_processed_previews(courseware, slides)

        VectorIndexService().rebuild_courseware_index(courseware, slides)
        debug_log(
            hypothesisId="H14",
            runId="pre-diagnose",
            location="learning/views.py:run_post_translation_tasks",
            message="Post translation tasks finished",
            data={"courseware_id": courseware.id},
        )
    except Exception as exc:
        debug_log(
            hypothesisId="H15",
            runId="pre-diagnose",
            location="learning/views.py:run_post_translation_tasks",
            message="Post translation tasks failed",
            data={"courseware_id": courseware_id, "exc_type": type(exc).__name__, "error": str(exc)[:500]},
        )



class MeView(APIView):
    """Return current user info to verify token validity."""
    # 返回当前登录用户的基础信息，用于前端确认访问令牌仍然有效。
    def get(self, request):
        return Response({
            "id": request.user.id,
            "username": request.user.username,
        })
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    # 处理 POST 请求，完成参数校验、业务调用和响应封装。
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user: User = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    # 处理 POST 请求，完成参数校验、业务调用和响应封装。
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]
        user = authenticate(username=username, password=password)
        if not user:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )


class CoursewareUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    # 处理 POST 请求，完成参数校验、业务调用和响应封装。
    def post(self, request):
        serializer = CoursewareUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # 上传、解析、渲染封面和创建页记录放在同一事务内，避免课件主表存在但页数据不完整。
            courseware: Courseware = serializer.save(owner=request.user)
            parsed_slides = PPTParserService.parse_courseware(courseware.file.path)
            sync_courseware_title_from_file(courseware)
            slide_images = SlideRenderService.export_slide_images(courseware.file.path, courseware.id)
            SlideContent.objects.bulk_create(
                [
                    SlideContent(
                        courseware=courseware,
                        slide_no=slide.slide_no,
                        source_image_url=slide_images.get(slide.slide_no, ""),
                        title=slide.title,
                        source_text=slide.source_text,
                        notes=slide.notes,
                        source_layout=slide.source_layout,
                    )
                    for slide in parsed_slides
                ]
            )
        return Response(
            {"courseware_id": courseware.id, "slide_count": len(parsed_slides), "title": courseware.title},
            status=status.HTTP_201_CREATED,
        )


class CoursewareListView(APIView):
    # 处理 GET 请求，按当前用户的权限边界读取数据并返回接口响应。
    def get(self, request):
        coursewares = list(Courseware.objects.filter(owner=request.user).order_by("-updated_at", "-id"))
        for courseware in coursewares:
            sync_courseware_title_from_file(courseware)
        return Response(
            [
                {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status,
                    "last_error": item.last_error,
                    "translation_duration_seconds": build_translation_duration_seconds(item),
                    "translation_total_chunks": item.translation_total_chunks,
                    "translation_completed_chunks": item.translation_completed_chunks,
                    "translation_current_slide_no": item.translation_current_slide_no,
                    "created_at": item.created_at,
                    **build_courseware_progress(item),
                }
                for item in coursewares
            ]
        )


class TranslateCoursewareView(APIView):
    # 处理 POST 请求，完成参数校验、业务调用和响应封装。
    def post(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)
        force = str(request.query_params.get("force", "0")).lower() in {"1", "true", "yes"}

        if courseware.status == Courseware.STATUS_TRANSLATING:
            return Response({"status": courseware.status, "courseware_id": courseware.id}, status=status.HTTP_202_ACCEPTED)
        if courseware.status == Courseware.STATUS_TRANSLATED and not force:
            return Response({"status": courseware.status, "courseware_id": courseware.id}, status=status.HTTP_200_OK)

        courseware.status = Courseware.STATUS_TRANSLATING
        # 每次重新翻译都重置进度字段，前端轮询时才能区分旧任务进度和当前任务进度。
        courseware.last_error = ""
        courseware.translation_started_at = timezone.now()
        courseware.translation_duration_seconds = None
        courseware.translation_total_chunks = 0
        courseware.translation_completed_chunks = 0
        courseware.translation_current_slide_no = None
        courseware.save(
            update_fields=[
                "status",
                "last_error",
                "translation_started_at",
                "translation_duration_seconds",
                "translation_total_chunks",
                "translation_completed_chunks",
                "translation_current_slide_no",
                "updated_at",
            ]
        )

        # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
        def _translate_job(courseware_id: int, owner_id: int) -> None:
            # 后台线程重新按 owner_id 取对象，避免跨用户访问，也避免复用请求线程里的数据库连接。
            close_old_connections()
            try:
                cw = Courseware.objects.get(id=courseware_id, owner_id=owner_id)
                translator = TranslationService()
                slides = translator.translate_courseware(cw)
                threading.Thread(target=run_post_translation_tasks, args=(cw.id, owner_id), daemon=True).start()
                debug_log(
                    hypothesisId="H6",
                    runId="pre-diagnose",
                    location="learning/views.py:_translate_job",
                    message="Background translation finished",
                    data={"courseware_id": cw.id, "final_status": cw.status, "translated_slides": len(slides)},
                )
            except Exception as exc:
                cw = Courseware.objects.filter(id=courseware_id, owner_id=owner_id).first()
                if cw:
                    cw.status = Courseware.STATUS_FAILED
                    cw.last_error = str(exc)[:500]
                    if cw.translation_started_at:
                        cw.translation_duration_seconds = max(
                            int((timezone.now() - cw.translation_started_at).total_seconds()),
                            0,
                        )
                    cw.save(update_fields=["status", "last_error", "translation_duration_seconds", "updated_at"])
                debug_log(
                    hypothesisId="H7",
                    runId="pre-diagnose",
                    location="learning/views.py:_translate_job",
                    message="Background translation failed",
                    data={
                        "courseware_id": courseware_id,
                        "exc_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    },
                )

        debug_log(
            hypothesisId="H6",
            runId="pre-diagnose",
            location="learning/views.py:TranslateCoursewareView.post",
            message="Starting background translation job",
            data={"courseware_id": courseware.id, "owner_id": request.user.id},
        )
        threading.Thread(target=_translate_job, args=(courseware.id, request.user.id), daemon=True).start()
        return Response({"status": Courseware.STATUS_TRANSLATING, "courseware_id": courseware.id}, status=status.HTTP_202_ACCEPTED)


class CoursewareStatusView(APIView):
    # 处理 GET 请求，按当前用户的权限边界读取数据并返回接口响应。
    def get(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)
        sync_courseware_title_from_file(courseware)
        progress = build_courseware_progress(courseware)
        return Response(
            {
                "id": courseware.id,
                "title": courseware.title,
                "status": courseware.status,
                "last_error": courseware.last_error,
                "translation_duration_seconds": build_translation_duration_seconds(courseware),
                "translation_total_chunks": courseware.translation_total_chunks,
                "translation_completed_chunks": courseware.translation_completed_chunks,
                "translation_current_slide_no": courseware.translation_current_slide_no,
                "updated_at": courseware.updated_at,
                **progress,
            }
        )


class ExportTranslatedPPTView(APIView):
    # 处理 GET 请求，按当前用户的权限边界读取数据并返回接口响应。
    def get(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)

        slides = list(courseware.slides.order_by("slide_no", "id"))
        slides_data = build_translated_slides_data(slides)
        if not slides_data:
            return Response({"detail": "No translated slides available for export."}, status=status.HTTP_400_BAD_REQUEST)

        output_path = ImageProcessingService.translated_output_path(courseware.id, courseware.file.path)
        # 导出文件按需生成：已存在就复用，减少重复渲染；不存在再根据当前译文布局生成。
        if not output_path.exists():
            generated = ImageProcessingService.export_translated_courseware(
                courseware.id,
                slides_data,
                courseware.file.path,
            )
            if generated is None or not generated.exists():
                return Response({"detail": "Failed to generate translated file."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            output_path = generated

        # 文件名需要过滤 Windows/浏览器不接受的字符，避免下载头或本地保存失败。
        safe_title = re.sub(r'[\\/:*?"<>|]+', "_", str(courseware.title or "").strip()) or f"courseware_{courseware.id}"
        filename = f"{safe_title}_translated{output_path.suffix.lower()}"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        response = FileResponse(open(output_path, "rb"), as_attachment=True, filename=filename, content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        return response


class CoursewareSlidesView(APIView):
    # 处理 GET 请求，按当前用户的权限边界读取数据并返回接口响应。
    def get(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)
        slides = courseware.slides.order_by("slide_no", "id")
        return Response(SlideContentSerializer(slides, many=True).data)


class TranslateSlideNotesView(APIView):
    # 处理 POST 请求，完成参数校验、业务调用和响应封装。
    def post(self, request, pk: int, slide_no: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)

        slide = courseware.slides.filter(slide_no=slide_no).first()
        if not slide:
            return Response({"detail": "Slide not found."}, status=status.HTTP_404_NOT_FOUND)
        if not (slide.notes or "").strip():
            return Response({"detail": "This slide has no notes."}, status=status.HTTP_400_BAD_REQUEST)

        translator = TranslationService()
        slide.translated_notes = translator.translate_notes_text(slide.notes, translator._build_term_hint())
        slide.save(update_fields=["translated_notes"])
        return Response(
            {
                "slide_no": slide.slide_no,
                "translated_notes": slide.translated_notes,
            }
        )


class QAView(APIView):
    # 处理 POST 请求，完成参数校验、业务调用和响应封装。
    def post(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = QARequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["question"]
        history = serializer.validated_data.get("history", [])
        slide_no = serializer.validated_data.get("slide_no")
        use_global_scope = serializer.validated_data.get("use_global_scope", True)
        answer, citations = QAService().ask(
            courseware,
            question,
            slide_no=slide_no,
            use_global_scope=use_global_scope,
            history=history,
        )
        record = QARecord.objects.create(
            courseware=courseware,
            user=request.user,
            question=question,
            answer=answer,
            citations=citations,
        )
        return Response(
            {
                "id": record.id,
                "question": question,
                "answer": answer,
                "citations": citations,
                "slide_no": slide_no,
                "use_global_scope": use_global_scope,
                "created_at": record.created_at,
            }
        )


class SummaryView(APIView):
    # 处理 POST 请求，完成参数校验、业务调用和响应封装。
    def post(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)

        summary_service = SummaryService()
        chapter_summary, key_points, term_pairs, mind_map = summary_service.generate(courseware)
        learning_suggestions = summary_service.generate_learning_suggestions(
            chapter_summary,
            key_points,
            term_pairs,
            mind_map,
            courseware.title,
        )
        record = SummaryRecord.objects.create(
            courseware=courseware,
            user=request.user,
            chapter_summary=chapter_summary,
            key_points=key_points,
            term_pairs=term_pairs,
            learning_suggestions=learning_suggestions,
            mind_map=mind_map,
        )
        return Response(
            {
                "id": record.id,
                "chapter_summary": chapter_summary,
                "key_points": key_points,
                "term_pairs": term_pairs,
                "learning_suggestions": learning_suggestions,
                "mind_map": mind_map,
                "created_at": record.created_at,
            }
        )


class RecordsView(APIView):
    # 处理 GET 请求，按当前用户的权限边界读取数据并返回接口响应。
    def get(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)
        qa_records = QARecordSerializer(courseware.qa_records.order_by("-created_at", "-id"), many=True).data
        summary_records = SummaryRecordSerializer(
            courseware.summary_records.order_by("-created_at", "-id"),
            many=True,
        ).data
        for item in summary_records:
            # 旧记录可能没有 learning_suggestions 字段内容，这里即时补一个本地兜底，保证历史数据仍可展示。
            if item.get("learning_suggestions"):
                continue
            chapter_summary = str(item.get("chapter_summary", "")).strip()
            key_points = item.get("key_points", []) if isinstance(item.get("key_points", []), list) else []
            term_pairs = item.get("term_pairs", []) if isinstance(item.get("term_pairs", []), list) else []
            item["learning_suggestions"] = SummaryService.build_learning_suggestions(
                chapter_summary,
                key_points,
                term_pairs,
            )
        return Response({"qa_records": qa_records, "summary_records": summary_records})
