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


def sync_courseware_title_from_file(courseware: Courseware) -> None:
    # Keep the upload-time title as source of truth (preserves original filename
    # and duplicate numbering like "(2)"), only backfill when title is empty.
    if str(courseware.title or "").strip():
        return
    file_name = Path(getattr(courseware.file, "name", "") or "").stem.strip()
    if file_name:
        courseware.title = file_name
        courseware.save(update_fields=["title", "updated_at"])


def build_courseware_progress(courseware: Courseware) -> dict:
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


def build_translation_duration_seconds(courseware: Courseware) -> int | None:
    started_at = courseware.translation_started_at
    if not started_at:
        return courseware.translation_duration_seconds
    if courseware.status == Courseware.STATUS_TRANSLATING:
        return max(int((timezone.now() - started_at).total_seconds()), 0)
    if courseware.translation_duration_seconds is not None:
        return courseware.translation_duration_seconds
    return max(int((timezone.now() - started_at).total_seconds()), 0)


def build_translated_slides_data(slides: list[SlideContent]) -> list[dict]:
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


def run_post_translation_tasks(courseware_id: int, owner_id: int) -> None:
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


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

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

    def post(self, request):
        serializer = CoursewareUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
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
                    "created_at": item.created_at,
                    **build_courseware_progress(item),
                }
                for item in coursewares
            ]
        )


class TranslateCoursewareView(APIView):
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
        courseware.last_error = ""
        courseware.translation_started_at = timezone.now()
        courseware.translation_duration_seconds = None
        courseware.save(
            update_fields=["status", "last_error", "translation_started_at", "translation_duration_seconds", "updated_at"]
        )

        def _translate_job(courseware_id: int, owner_id: int) -> None:
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
                "updated_at": courseware.updated_at,
                **progress,
            }
        )


class ExportTranslatedPPTView(APIView):
    def get(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)

        slides = list(courseware.slides.order_by("slide_no", "id"))
        slides_data = build_translated_slides_data(slides)
        if not slides_data:
            return Response({"detail": "No translated slides available for export."}, status=status.HTTP_400_BAD_REQUEST)

        output_path = ImageProcessingService.translated_output_path(courseware.id, courseware.file.path)
        if not output_path.exists():
            generated = ImageProcessingService.export_translated_courseware(
                courseware.id,
                slides_data,
                courseware.file.path,
            )
            if generated is None or not generated.exists():
                return Response({"detail": "Failed to generate translated file."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            output_path = generated

        safe_title = re.sub(r'[\\/:*?"<>|]+', "_", str(courseware.title or "").strip()) or f"courseware_{courseware.id}"
        filename = f"{safe_title}_translated{output_path.suffix.lower()}"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        response = FileResponse(open(output_path, "rb"), as_attachment=True, filename=filename, content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        return response


class CoursewareSlidesView(APIView):
    def get(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)
        slides = courseware.slides.order_by("slide_no", "id")
        return Response(SlideContentSerializer(slides, many=True).data)


class TranslateSlideNotesView(APIView):
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
    def post(self, request, pk: int):
        courseware = Courseware.objects.filter(id=pk, owner=request.user).first()
        if not courseware:
            return Response({"detail": "Courseware not found."}, status=status.HTTP_404_NOT_FOUND)

        summary_service = SummaryService()
        chapter_summary, key_points, term_pairs, mind_map = summary_service.generate(courseware)
        learning_suggestions = summary_service.build_learning_suggestions(chapter_summary, key_points, term_pairs)
        record = SummaryRecord.objects.create(
            courseware=courseware,
            user=request.user,
            chapter_summary=chapter_summary,
            key_points=key_points,
            term_pairs=term_pairs,
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
            chapter_summary = str(item.get("chapter_summary", "")).strip()
            key_points = item.get("key_points", []) if isinstance(item.get("key_points", []), list) else []
            term_pairs = item.get("term_pairs", []) if isinstance(item.get("term_pairs", []), list) else []
            item["learning_suggestions"] = SummaryService.build_learning_suggestions(
                chapter_summary,
                key_points,
                term_pairs,
            )
        return Response({"qa_records": qa_records, "summary_records": summary_records})
