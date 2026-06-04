from __future__ import annotations

import re
import shutil
from pathlib import Path

from django.conf import settings

from app.debug_logger import debug_log

from .ppt_parser_service import PPTParserService


class SlideRenderService:
    """
    Export each PPT slide to PNG via local PowerPoint COM on Windows.
    Returns {slide_no: media_url}.
    """

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _image_sort_key(image_path: Path) -> tuple[int, str]:
        stem = image_path.stem
        match = re.search(r"(\d+)$", stem)
        if match:
            return int(match.group(1)), stem
        return 10**9, stem

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _prepare_export_dir(courseware_id: int, output_folder: str) -> Path:
        export_dir = Path(settings.MEDIA_ROOT) / output_folder / f"courseware_{courseware_id}"
        if export_dir.exists():
            shutil.rmtree(export_dir, ignore_errors=True)
        export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _build_image_urls(export_dir: Path, courseware_id: int, output_folder: str) -> dict[int, str]:
        image_urls: dict[int, str] = {}
        for index, image_path in enumerate(sorted(export_dir.glob("*.PNG"), key=SlideRenderService._image_sort_key), start=1):
            image_urls[index] = f"{settings.MEDIA_URL}{output_folder}/courseware_{courseware_id}/{image_path.name}"

        if not image_urls:
            for index, image_path in enumerate(sorted(export_dir.glob("*.png"), key=SlideRenderService._image_sort_key), start=1):
                image_urls[index] = f"{settings.MEDIA_URL}{output_folder}/courseware_{courseware_id}/{image_path.name}"
        return image_urls

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _export_ppt_images(pptx_path: str, courseware_id: int, output_folder: str = "rendered_slides") -> dict[int, str]:
        try:
            import pythoncom
            from win32com.client import DispatchEx
        except Exception:
            return {}

        pythoncom.CoInitialize()
        powerpoint = None
        presentation = None
        try:
            export_dir = SlideRenderService._prepare_export_dir(courseware_id, output_folder)

            powerpoint = DispatchEx("PowerPoint.Application")
            try:
                powerpoint.Visible = 0
                powerpoint.DisplayAlerts = 0
            except Exception:
                pass
            presentation = powerpoint.Presentations.Open(str(Path(pptx_path).resolve()), WithWindow=False)
            presentation.SaveAs(str(export_dir), 18)  # ppSaveAsPNG

            return SlideRenderService._build_image_urls(export_dir, courseware_id, output_folder)
        finally:
            if presentation is not None:
                try:
                    presentation.Close()
                except Exception:
                    pass
            if powerpoint is not None:
                try:
                    powerpoint.Quit()
                except Exception:
                    pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _export_pdf_images(pdf_path: str, courseware_id: int, output_folder: str = "rendered_slides") -> dict[int, str]:
        try:
            import fitz  # type: ignore
        except Exception as exc:
            raise RuntimeError("PDF rendering requires PyMuPDF. Please install it with `pip install PyMuPDF`.") from exc

        render_dpi = max(int(getattr(settings, "PDF_RENDER_DPI", 144) or 72), 72)
        zoom = max(float(render_dpi) / 72.0, 1.0)
        matrix = fitz.Matrix(zoom, zoom)
        export_dir = SlideRenderService._prepare_export_dir(courseware_id, output_folder)

        document = None
        try:
            document = fitz.open(str(Path(pdf_path).resolve()))
            for index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image_path = export_dir / f"幻灯片{index}.PNG"
                pixmap.save(str(image_path))
            return SlideRenderService._build_image_urls(export_dir, courseware_id, output_folder)
        finally:
            if document is not None:
                try:
                    document.close()
                except Exception:
                    pass

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def export_slide_images(source_path: str, courseware_id: int, output_folder: str = "rendered_slides") -> dict[int, str]:
        suffix = str(Path(source_path).suffix or "").strip().lower()
        if PPTParserService.is_pdf_file(source_path):
            return SlideRenderService._export_pdf_images(source_path, courseware_id, output_folder)
        if suffix in set(PPTParserService.PPT_FORMATS):
            return SlideRenderService._export_ppt_images(source_path, courseware_id, output_folder)
        debug_log(
            hypothesisId="H10",
            runId="pre-diagnose",
            location="slide_render_service:export_slide_images",
            message="Unsupported source format for rendering",
            data={"suffix": suffix, "source_path": str(source_path)[:300]},
        )
        return {}
