from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone
from PIL import Image

from app.debug_logger import debug_log

from learning.models import Courseware, SlideContent, TermDictionary, TranslationCache

from .image_processing_service import ImageProcessingService
from .llm_client import ChatMessage, OpenAICompatibleClient
from .ppt_parser_service import PPTParserService


class TranslationService:
    CACHE_SCHEMA_VERSION = "v1"
    CACHE_TYPE_SLIDE_TEXT = "slide_text"
    CACHE_TYPE_NOTES = "slide_notes"
    CACHE_TYPE_CONTAINER = "container_text"
    CACHE_TYPE_IMAGE_OCR = "image_ocr_text"
    DEFAULT_SOURCE_LANGUAGE = "en"
    DEFAULT_TARGET_LANGUAGE = "zh"

    def __init__(self):
        self.client = OpenAICompatibleClient()
        self.max_workers = max(int(getattr(settings, "TRANSLATION_MAX_WORKERS", 4) or 1), 1)
        self.chunk_max_containers = max(
            int(getattr(settings, "TRANSLATION_CHUNK_MAX_CONTAINERS", 16) or 1),
            1,
        )
        self.chunk_max_chars = max(
            int(getattr(settings, "TRANSLATION_CHUNK_MAX_CHARS", 7000) or 200),
            200,
        )
        self.image_ocr_enabled = bool(getattr(settings, "TRANSLATION_IMAGE_OCR_ENABLED", True))
        self.image_ocr_max_containers_per_slide = max(
            int(getattr(settings, "TRANSLATION_IMAGE_OCR_MAX_CONTAINERS_PER_SLIDE", 3) or 1),
            1,
        )
        self.image_ocr_min_area_ratio = max(
            float(getattr(settings, "TRANSLATION_IMAGE_OCR_MIN_AREA_RATIO", 0.015) or 0.001),
            0.001,
        )

    @staticmethod
    def _build_term_hint() -> str:
        terms = TermDictionary.objects.all()[:200]
        if not terms:
            return ""
        pairs = "\n".join([f"{term.source_term} => {term.target_term}" for term in terms])
        return f"Fixed terminology mappings:\n{pairs}"

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    def _build_cache_key(self, text: str, term_hint: str, translation_type: str) -> str:
        source_text = (text or "").strip()
        term_hash = self._sha256((term_hint or "").strip())
        payload = "|".join(
            [
                self.CACHE_SCHEMA_VERSION,
                translation_type,
                self.client.model,
                self.DEFAULT_SOURCE_LANGUAGE,
                self.DEFAULT_TARGET_LANGUAGE,
                term_hash,
                source_text,
            ]
        )
        return self._sha256(payload)

    def _cache_lookup(self, text: str, term_hint: str, translation_type: str) -> str | None:
        source_text = (text or "").strip()
        if not source_text:
            return None
        cache_key = self._build_cache_key(source_text, term_hint, translation_type)
        try:
            cached = (
                TranslationCache.objects.filter(cache_key=cache_key)
                .only("translated_text")
                .first()
            )
        except DatabaseError:
            return None
        if not cached:
            return None
        translated = (cached.translated_text or "").strip()
        return translated or None

    def _cache_store(self, text: str, translated_text: str, term_hint: str, translation_type: str) -> None:
        source_text = (text or "").strip()
        translated = (translated_text or "").strip()
        if not source_text or not translated:
            return

        term_hash = self._sha256((term_hint or "").strip())
        try:
            TranslationCache.objects.bulk_create(
                [
                    TranslationCache(
                        cache_key=self._build_cache_key(source_text, term_hint, translation_type),
                        translation_type=translation_type,
                        source_language=self.DEFAULT_SOURCE_LANGUAGE,
                        target_language=self.DEFAULT_TARGET_LANGUAGE,
                        model_name=self.client.model,
                        term_hint_hash=term_hash,
                        source_hash=self._sha256(source_text),
                        source_text=source_text,
                        translated_text=translated,
                    )
                ],
                ignore_conflicts=True,
            )
        except DatabaseError:
            return

    def _translate_text(
        self,
        text: str,
        term_hint: str,
        translation_type: str = CACHE_TYPE_SLIDE_TEXT,
    ) -> str:
        src = (text or "").strip()
        if not src:
            return ""

        cached = self._cache_lookup(src, term_hint, translation_type)
        if cached is not None:
            return cached

        system_prompt = (
            "You are a bilingual course translation assistant. "
            "Translate English course slide content into Simplified Chinese. "
            "Keep technical terms consistent and concise."
        )
        user_prompt = (
            f"{term_hint}\n\n"
            "Requirements:\n"
            "1) Preserve list structure and key terminology.\n"
            "2) Do not add unrelated explanations.\n"
            "3) Return only translated Chinese text.\n\n"
            f"Text to translate:\n{src}"
        )
        translated = self.client.chat(
            [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)],
            temperature=0.1,
        )
        self._cache_store(src, translated, term_hint, translation_type)
        return translated

    def translate_notes_text(self, text: str, term_hint: str = "") -> str:
        src = (text or "").strip()
        if not src:
            return ""

        cached = self._cache_lookup(src, term_hint, self.CACHE_TYPE_NOTES)
        if cached is not None:
            return cached

        system_prompt = (
            "You are a bilingual course translation assistant. "
            "Translate slide speaker notes into concise Simplified Chinese. "
            "Preserve list structure and teaching meaning."
        )
        user_prompt = (
            f"{term_hint}\n\n"
            "Requirements:\n"
            "1) Keep paragraph and list structure as much as possible.\n"
            "2) Do not add extra explanation.\n"
            "3) Return only translated Chinese text.\n\n"
            f"Notes to translate:\n{src}"
        )
        translated = self.client.chat(
            [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)],
            temperature=0.1,
        )
        self._cache_store(src, translated, term_hint, self.CACHE_TYPE_NOTES)
        return translated

    @staticmethod
    def _extract_json_payload(content: str) -> str:
        cleaned = (content or "").strip()
        if not cleaned:
            raise ValueError("Empty translation response.")

        fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL)
        if fenced:
            return fenced.group(1).strip()

        start = min([idx for idx in [cleaned.find("["), cleaned.find("{")] if idx != -1], default=-1)
        if start == -1:
            return cleaned

        end_array = cleaned.rfind("]")
        end_object = cleaned.rfind("}")
        end = max(end_array, end_object)
        if end >= start:
            return cleaned[start : end + 1].strip()
        return cleaned

    @staticmethod
    def _normalize_lines(lines: list[str]) -> list[str]:
        return [str(line).strip() for line in lines if str(line).strip()]

    @staticmethod
    def _resolve_media_path(media_url: str) -> Path | None:
        normalized = str(media_url or "").strip()
        if not normalized:
            return None
        media_prefix = str(getattr(settings, "MEDIA_URL", "") or "")
        if media_prefix and normalized.startswith(media_prefix):
            normalized = normalized[len(media_prefix) :]
        normalized = normalized.lstrip("/\\")
        path = Path(settings.MEDIA_ROOT) / Path(normalized)
        return path if path.exists() else None

    @staticmethod
    def _container_area_ratio(container: dict) -> float:
        width = max(float(container.get("w", 0) or 0), 0.0)
        height = max(float(container.get("h", 0) or 0), 0.0)
        return width * height

    @staticmethod
    def _build_image_region_payload(image_path: Path, container: dict) -> tuple[str, str] | None:
        try:
            with Image.open(image_path) as img:
                rgb = img.convert("RGB")
                image_width, image_height = rgb.size
                left = max(int(float(container.get("x", 0) or 0) * image_width), 0)
                top = max(int(float(container.get("y", 0) or 0) * image_height), 0)
                width = max(int(float(container.get("w", 0) or 0) * image_width), 1)
                height = max(int(float(container.get("h", 0) or 0) * image_height), 1)
                right = min(left + width, image_width)
                bottom = min(top + height, image_height)
                if right <= left or bottom <= top:
                    return None

                region = rgb.crop((left, top, right, bottom))
                buffer = io.BytesIO()
                region.save(buffer, format="JPEG", quality=88)
                image_bytes = buffer.getvalue()
                image_digest = hashlib.sha256(image_bytes).hexdigest()
                image_base64 = base64.b64encode(image_bytes).decode("ascii")
                return f"data:image/jpeg;base64,{image_base64}", image_digest
        except Exception:
            return None

    def _extract_and_translate_image_region_text(self, image_data_url: str, term_hint: str) -> tuple[str, str]:
        system_prompt = (
            "You are an OCR + translation assistant for course slides. "
            "Extract visible text from the image region and translate between English and Simplified Chinese."
        )
        user_text = (
            f"{term_hint}\n\n"
            "Requirements:\n"
            "1) Extract only visible text in the image region.\n"
            "2) If source is mostly English, translate to Simplified Chinese; if source is mostly Chinese, translate to English.\n"
            "3) Keep concise line structure when possible.\n"
            '4) Return strict JSON only: {"source_text": "...", "translated_text": "..."}.\n'
            "5) If no readable text, both fields should be empty string.\n"
        )
        raw = self.client.chat(
            [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                ),
            ],
            temperature=0.1,
        )
        source_text = ""
        translated_text = ""
        try:
            parsed = json.loads(self._extract_json_payload(str(raw or "")))
            if isinstance(parsed, dict):
                source_text = str(parsed.get("source_text", "")).strip()
                translated_text = str(parsed.get("translated_text", "")).strip()
        except Exception:
            translated_text = str(raw or "").strip()
        return source_text, translated_text

    def _translate_image_containers(
        self,
        slide: SlideContent,
        image_containers: list[dict],
        term_hint: str,
    ) -> tuple[dict[int, dict], dict[int, str]]:
        if not self.image_ocr_enabled or not image_containers:
            return {}, {}

        image_path = self._resolve_media_path(str(slide.source_image_url or ""))
        if image_path is None:
            return {}, {}

        sorted_candidates = sorted(
            image_containers,
            key=self._container_area_ratio,
            reverse=True,
        )
        limited_candidates = sorted_candidates[: self.image_ocr_max_containers_per_slide]
        translated_map: dict[int, dict] = {}
        source_text_map: dict[int, str] = {}

        for container in limited_candidates:
            if self._container_area_ratio(container) < self.image_ocr_min_area_ratio:
                continue

            container_id = int(container.get("container_id") or 0)
            if not container_id:
                continue

            payload = self._build_image_region_payload(image_path, container)
            if payload is None:
                continue
            image_data_url, image_digest = payload
            source_token = (
                f"imgocr:v2:{slide.id}:{container_id}:{image_digest}:"
                f"{round(float(container.get('x', 0) or 0), 4)}:"
                f"{round(float(container.get('y', 0) or 0), 4)}:"
                f"{round(float(container.get('w', 0) or 0), 4)}:"
                f"{round(float(container.get('h', 0) or 0), 4)}"
            )

            source_text = ""
            translated_text = ""
            cached_payload = self._cache_lookup(source_token, term_hint, self.CACHE_TYPE_IMAGE_OCR)
            if cached_payload is None:
                try:
                    source_text, translated_text = self._extract_and_translate_image_region_text(image_data_url, term_hint)
                except Exception as exc:
                    debug_log(
                        hypothesisId="H17",
                        runId="pre-diagnose",
                        location="translation_service:_translate_image_containers",
                        message="Image OCR translation failed",
                        data={
                            "slide_id": slide.id,
                            "slide_no": slide.slide_no,
                            "container_id": container_id,
                            "exc_type": type(exc).__name__,
                            "error": self._sanitize_error_text(exc),
                        },
                    )
                    continue
                self._cache_store(
                    source_token,
                    json.dumps(
                        {"source_text": source_text, "translated_text": translated_text},
                        ensure_ascii=False,
                    ),
                    term_hint,
                    self.CACHE_TYPE_IMAGE_OCR,
                )
            else:
                try:
                    parsed_cache = json.loads(cached_payload)
                    if isinstance(parsed_cache, dict):
                        source_text = str(parsed_cache.get("source_text", "")).strip()
                        translated_text = str(parsed_cache.get("translated_text", "")).strip()
                    else:
                        translated_text = str(cached_payload or "").strip()
                except Exception:
                    translated_text = str(cached_payload or "").strip()

            translated_text = str(translated_text or "").strip()
            if not translated_text:
                continue
            translated_map[container_id] = {
                "text": translated_text,
                "paragraphs": self._normalize_lines(translated_text.splitlines()) or [translated_text],
            }
            if source_text:
                source_text_map[container_id] = source_text

        return translated_map, source_text_map

    @staticmethod
    def _split_to_match_paragraphs(text: str, source_paragraphs: list[str], translated_paragraphs: list[str] | None = None) -> list[str]:
        source_count = max(len(source_paragraphs), 1)
        cleaned_text = str(text or "").strip()

        response_lines = TranslationService._normalize_lines(translated_paragraphs or [])
        if not response_lines:
            response_lines = TranslationService._normalize_lines(cleaned_text.splitlines())
        if not response_lines:
            response_lines = [cleaned_text] if cleaned_text else [""]

        if source_count == 1:
            return ["\n".join(response_lines).strip()]

        if len(response_lines) == source_count:
            return response_lines

        # Cached/LLM responses occasionally collapse multi-paragraph text into one line.
        # Returning that one line is better than padding many empty lines (which makes
        # later pages appear as "not translated" in the preview).
        if len(response_lines) == 1 and source_count > 1:
            return [response_lines[0]]

        if len(response_lines) < source_count:
            return response_lines + [""] * (source_count - len(response_lines))

        merged = response_lines[: source_count - 1]
        merged.append("\n".join(response_lines[source_count - 1 :]).strip())
        return merged

    def _chunk_payload_containers(self, payload_containers: list[dict]) -> list[list[dict]]:
        if not payload_containers:
            return []

        chunks: list[list[dict]] = []
        current_chunk: list[dict] = []
        current_chars = 0

        for container in payload_containers:
            text = str(container.get("text", ""))
            text_len = len(text)
            should_split = bool(current_chunk) and (
                len(current_chunk) >= self.chunk_max_containers
                or (current_chars + text_len) > self.chunk_max_chars
            )
            if should_split:
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0
            current_chunk.append(container)
            current_chars += text_len

        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def _load_cached_containers(self, payload_containers: list[dict], term_hint: str) -> tuple[dict[int, dict], list[dict]]:
        if not payload_containers:
            return {}, []

        containers_by_key: dict[str, list[dict]] = {}
        for container in payload_containers:
            source_text = str(container.get("text", "")).strip()
            if not source_text:
                continue
            cache_key = self._build_cache_key(source_text, term_hint, self.CACHE_TYPE_CONTAINER)
            enriched = dict(container)
            enriched["cache_key"] = cache_key
            containers_by_key.setdefault(cache_key, []).append(enriched)

        if not containers_by_key:
            return {}, []

        try:
            cache_entries = TranslationCache.objects.filter(cache_key__in=list(containers_by_key.keys())).only(
                "cache_key",
                "translated_text",
            )
        except DatabaseError:
            return {}, [dict(container) for container in payload_containers]
        cache_map = {entry.cache_key: (entry.translated_text or "").strip() for entry in cache_entries}

        cached_map: dict[int, dict] = {}
        pending: list[dict] = []
        for cache_key, grouped_containers in containers_by_key.items():
            translated = cache_map.get(cache_key, "")
            if translated:
                for container in grouped_containers:
                    cached_map[int(container.get("container_id") or 0)] = {"text": translated, "paragraphs": []}
                continue
            pending.extend(grouped_containers)

        return cached_map, pending

    def _cache_container_results(self, payload_containers: list[dict], translated_map: dict[int, dict], term_hint: str) -> None:
        if not payload_containers or not translated_map:
            return

        term_hash = self._sha256((term_hint or "").strip())
        rows_by_cache_key: dict[str, TranslationCache] = {}
        for container in payload_containers:
            container_id = int(container.get("container_id") or 0)
            if not container_id:
                continue
            translated_payload = translated_map.get(container_id, {})
            translated_text = str(translated_payload.get("text", "")).strip()
            source_text = str(container.get("text", "")).strip()
            if not source_text or not translated_text:
                continue
            cache_key = str(container.get("cache_key") or self._build_cache_key(source_text, term_hint, self.CACHE_TYPE_CONTAINER))
            rows_by_cache_key[cache_key] = TranslationCache(
                cache_key=cache_key,
                translation_type=self.CACHE_TYPE_CONTAINER,
                source_language=self.DEFAULT_SOURCE_LANGUAGE,
                target_language=self.DEFAULT_TARGET_LANGUAGE,
                model_name=self.client.model,
                term_hint_hash=term_hash,
                source_hash=self._sha256(source_text),
                source_text=source_text,
                translated_text=translated_text,
            )
        if rows_by_cache_key:
            try:
                TranslationCache.objects.bulk_create(list(rows_by_cache_key.values()), ignore_conflicts=True)
            except DatabaseError:
                return

    def _translate_containers_structured(self, payload_containers: list[dict], term_hint: str, *, is_retry: bool = False) -> dict[int, dict]:
        if not payload_containers:
            return {}

        expected_ids = {int(item.get("container_id") or 0) for item in payload_containers}
        expected_ids.discard(0)
        if not expected_ids:
            return {}

        system_prompt = (
            "You are a bilingual course translation assistant. "
            "Translate editable PPT text containers into Simplified Chinese. "
            "Return strict JSON only."
        )
        retry_hint = ""
        if is_retry:
            retry_hint = (
                "Previous response was invalid or incomplete. "
                "This retry must include every container_id exactly once and return strict JSON only.\n"
            )
        user_prompt = (
            f"{term_hint}\n\n"
            f"{retry_hint}"
            "Requirements:\n"
            "1) Keep each text container independent. Do not merge or split containers.\n"
            "2) Preserve meaning, terminology, list structure, and paragraph boundaries as much as possible.\n"
            '3) Return a JSON array. Each item must be {"container_id": number, "text": "...", "paragraphs": ["..."]}.\n'
            "4) Every source container_id must appear exactly once in the response.\n"
            "5) paragraphs should keep the original paragraph count whenever possible.\n\n"
            f"Source blocks / containers:\n{json.dumps(payload_containers, ensure_ascii=False)}"
        )

        raw = self.client.chat(
            [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)],
            temperature=0.1,
        )
        try:
            parsed = json.loads(self._extract_json_payload(raw))
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}

        if not isinstance(parsed, list):
            return {}

        translated_map: dict[int, dict] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            container_id = int(item.get("container_id") or item.get("block_id") or 0)
            if container_id not in expected_ids:
                continue
            translated_text = str(item.get("text", "")).strip()
            if not translated_text:
                continue
            translated_map[container_id] = {
                "text": translated_text,
                "paragraphs": self._normalize_lines(item.get("paragraphs", [])),
            }
        return translated_map

    @staticmethod
    def _missing_payload_containers(payload_containers: list[dict], translated_map: dict[int, dict]) -> list[dict]:
        missing: list[dict] = []
        for container in payload_containers:
            container_id = int(container.get("container_id") or 0)
            translated_text = str(translated_map.get(container_id, {}).get("text", "")).strip()
            if not translated_text:
                missing.append(container)
        return missing

    def _translate_container_chunk(self, payload_containers: list[dict], term_hint: str) -> dict[int, dict]:
        translated_map = self._translate_containers_structured(payload_containers, term_hint, is_retry=False)

        missing = self._missing_payload_containers(payload_containers, translated_map)
        if missing:
            retry_map = self._translate_containers_structured(missing, term_hint, is_retry=True)
            translated_map.update(retry_map)
            missing = self._missing_payload_containers(payload_containers, translated_map)

        for container in missing:
            container_id = int(container.get("container_id") or 0)
            source_text = str(container.get("text", "")).strip()
            if not container_id or not source_text:
                continue
            translated_text = self._translate_text(
                source_text,
                term_hint,
                translation_type=self.CACHE_TYPE_CONTAINER,
            )
            translated_map[container_id] = {
                "text": translated_text,
                "paragraphs": self._split_to_match_paragraphs(
                    translated_text,
                    list(container.get("paragraphs", [])),
                ),
            }
        return translated_map

    def _translate_containers(self, containers: list[dict], term_hint: str) -> dict[int, dict]:
        payload_containers = []
        for container in containers:
            source_text = str(container.get("text", "")).strip()
            if not source_text:
                continue
            payload_containers.append(
                {
                    "container_id": int(container.get("container_id") or 0),
                    "text": source_text,
                    "paragraphs": container.get("paragraphs", []),
                    "is_title": bool(container.get("is_title", False)),
                }
            )

        if not payload_containers:
            return {}

        cached_map, pending_containers = self._load_cached_containers(payload_containers, term_hint)
        translated_map: dict[int, dict] = dict(cached_map)
        if not pending_containers:
            return translated_map

        chunks = self._chunk_payload_containers(pending_containers)
        for chunk in chunks:
            chunk_map = self._translate_container_chunk(chunk, term_hint)
            translated_map.update(chunk_map)
            self._cache_container_results(chunk, chunk_map, term_hint)
        return translated_map

    def _build_translated_layout(self, slide: SlideContent, term_hint: str) -> tuple[str, dict, str]:
        source_layout = copy.deepcopy(slide.source_layout or {})
        source_containers = source_layout.get("text_containers", []) or []
        if not source_containers:
            source_containers = []
            for block in source_layout.get("blocks", []):
                source_containers.append(
                    {
                        "container_id": int(block.get("container_id") or block.get("block_id") or 0),
                        "container_key": f"fallback:{block.get('block_id', 0)}",
                        "shape_id": int(block.get("shape_id") or 0),
                        "shape_path": "",
                        "kind": "text_frame",
                        "paragraphs": [str(block.get("text", "")).strip()],
                        "text": str(block.get("text", "")).strip(),
                        "x": block.get("x", 0),
                        "y": block.get("y", 0),
                        "w": block.get("w", 0),
                        "h": block.get("h", 0),
                        "is_title": bool(block.get("is_title", False)),
                    }
                )

        is_pdf_source = False
        try:
            is_pdf_source = PPTParserService.is_pdf_file(slide.courseware.file.path)
        except Exception:
            is_pdf_source = False
        if is_pdf_source:
            source_containers = PPTParserService.dedupe_pdf_repeated_short_phrases(source_containers)

        text_containers = [item for item in source_containers if str(item.get("kind", "")) != "image_ocr"]
        image_containers = [item for item in source_containers if str(item.get("kind", "")) == "image_ocr"]

        translated_map = self._translate_containers(text_containers, term_hint)
        image_translated_map, image_source_text_map = self._translate_image_containers(slide, image_containers, term_hint)
        translated_map.update(image_translated_map)
        translated_containers: list[dict] = []
        translated_blocks: list[dict] = []
        translated_texts: list[str] = []
        source_ocr_texts: list[str] = []

        for source_container in source_containers:
            container_id = int(source_container.get("container_id") or 0)
            if str(source_container.get("kind", "")) == "image_ocr":
                source_ocr_text = str(image_source_text_map.get(container_id, "")).strip()
                if source_ocr_text:
                    source_container["text"] = source_ocr_text
                    source_container["paragraphs"] = self._normalize_lines(source_ocr_text.splitlines()) or [source_ocr_text]
                    source_ocr_texts.append(source_ocr_text)
            translated_payload = translated_map.get(container_id, {})
            translated_text = str(translated_payload.get("text", "")).strip()
            translated_paragraphs = self._split_to_match_paragraphs(
                translated_text,
                list(source_container.get("paragraphs", [])),
                translated_payload.get("paragraphs", []),
            )

            translated_container = dict(source_container)
            translated_container["translated_text"] = translated_text
            translated_container["translated_paragraphs"] = translated_paragraphs
            translated_container["text"] = translated_text
            translated_container["paragraphs"] = translated_paragraphs
            translated_container["font_name"] = source_container.get("font_name", "")
            translated_container["font_size_pt"] = source_container.get("font_size_pt")
            translated_containers.append(translated_container)
            if translated_text:
                translated_texts.append(translated_text)

            paragraph_height = float(source_container.get("h", 0) or 0) / max(len(translated_paragraphs), 1)
            for paragraph_index, paragraph_text in enumerate(translated_paragraphs):
                translated_blocks.append(
                    {
                        "block_id": len(translated_blocks) + 1,
                        "container_id": container_id,
                        "paragraph_index": paragraph_index,
                        "shape_id": source_container.get("shape_id", 0),
                        "kind": source_container.get("kind", "text_frame"),
                        "text": paragraph_text,
                        "x": source_container.get("x", 0),
                        "y": float(source_container.get("y", 0) or 0) + paragraph_index * paragraph_height,
                        "w": source_container.get("w", 0),
                        "h": paragraph_height,
                        "is_title": bool(source_container.get("is_title", False) and paragraph_index == 0),
                        "font_name": source_container.get("font_name", ""),
                        "font_size_pt": source_container.get("font_size_pt"),
                    }
                )

        translated_layout = {
            "page_width": source_layout.get("page_width", 1),
            "page_height": source_layout.get("page_height", 1),
            "blocks": translated_blocks,
            "text_containers": translated_containers,
        }
        if is_pdf_source:
            base_source_text = "\n".join(
                [
                    str(container.get("text", "")).strip()
                    for container in text_containers
                    if str(container.get("text", "")).strip()
                ]
            ).strip()
        else:
            base_source_text = str(slide.source_text or "").strip()
        deduped_ocr: list[str] = []
        for item in source_ocr_texts:
            value = str(item or "").strip()
            if not value:
                continue
            if value in base_source_text:
                continue
            if value in deduped_ocr:
                continue
            deduped_ocr.append(value)

        enhanced_source_text = base_source_text
        if deduped_ocr:
            ocr_block = "[Image OCR]\n" + "\n".join(deduped_ocr)
            enhanced_source_text = "\n\n".join([part for part in [base_source_text, ocr_block] if part]).strip()
        return "\n".join(translated_texts).strip(), translated_layout, enhanced_source_text

    def _translate_single_slide(self, slide: SlideContent, term_hint: str) -> tuple[int, str, dict, str]:
        translated_text, translated_layout, enhanced_source_text = self._build_translated_layout(slide, term_hint)
        return slide.id, translated_text, translated_layout, enhanced_source_text

    @staticmethod
    def _sanitize_error_text(exc: Exception) -> str:
        return " ".join(str(exc).split())[:240]

    @staticmethod
    def _has_textual_source(source_text: str, source_layout: dict | None) -> bool:
        if str(source_text or "").strip():
            return True
        layout = source_layout or {}
        containers = layout.get("text_containers", []) or []
        for container in containers:
            if str(container.get("kind", "")) == "image_ocr":
                continue
            if str(container.get("text", "")).strip():
                return True
        return False

    def _build_failure_summary(self, failed_slides: list[tuple[int, Exception]], total: int) -> str:
        if not failed_slides:
            return ""
        first_slide_no, first_exc = failed_slides[0]
        first_error = self._sanitize_error_text(first_exc)
        return (
            f"共有 {len(failed_slides)}/{total} 页翻译失败。"
            f"首个失败页：第 {first_slide_no} 页。错误：{first_error}"
        )

    def _mark_slide_translation_result(
        self,
        slide: SlideContent,
        translated_text: str,
        translated_layout: dict,
        source_text: str,
    ) -> bool:
        has_source = self._has_textual_source(source_text, slide.source_layout or {})
        is_done = bool((translated_text or "").strip()) or not has_source
        slide.source_text = source_text
        slide.translated_text = translated_text
        slide.translated_layout = translated_layout
        SlideContent.objects.filter(id=slide.id).update(
            source_text=source_text,
            translated_text=translated_text,
            translated_layout=translated_layout,
            translation_done=is_done,
        )
        return is_done

    @staticmethod
    def _mark_slide_translation_failed(slide: SlideContent) -> None:
        SlideContent.objects.filter(id=slide.id).update(translation_done=False)

    def build_processed_previews(self, courseware: Courseware, slides: list[SlideContent]) -> None:
        slides_data = [
            {
                "slide_no": slide.slide_no,
                "source_image_url": slide.source_image_url,
                "source_layout": slide.source_layout,
                "translated_layout": slide.translated_layout,
            }
            for slide in slides
            if slide.translated_layout
        ]
        if not slides_data:
            return

        processed_urls = ImageProcessingService.process_all_slides(courseware.id, slides_data, courseware.file.path)
        for slide in slides:
            if slide.slide_no in processed_urls:
                slide.processed_image_url = processed_urls[slide.slide_no]
                slide.preview_done = True
        slides_to_update = [slide for slide in slides if slide.processed_image_url]
        if slides_to_update:
            SlideContent.objects.bulk_update(slides_to_update, ["processed_image_url", "preview_done"])

    def translate_courseware(self, courseware: Courseware):
        term_hint = self._build_term_hint()
        slides = list(courseware.slides.order_by("slide_no", "id"))
        failed_slides: list[tuple[int, Exception]] = []
        translated_count = 0
        started_at = courseware.translation_started_at

        if not slides:
            courseware.status = Courseware.STATUS_TRANSLATED
            courseware.last_error = ""
            if started_at:
                courseware.translation_duration_seconds = max(
                    int((timezone.now() - started_at).total_seconds()),
                    0,
                )
            courseware.save(update_fields=["status", "last_error", "translation_duration_seconds", "updated_at"])
            return []

        max_workers = min(self.max_workers, len(slides))
        if max_workers <= 1:
            for slide in slides:
                try:
                    _, translated_text, translated_layout, enhanced_source_text = self._translate_single_slide(slide, term_hint)
                    if self._mark_slide_translation_result(slide, translated_text, translated_layout, enhanced_source_text):
                        translated_count += 1
                except Exception as exc:
                    failed_slides.append((slide.slide_no, exc))
                    self._mark_slide_translation_failed(slide)
                    debug_log(
                        hypothesisId="H16",
                        runId="pre-diagnose",
                        location="translation_service:translate_courseware",
                        message="Single slide translation failed in sequential mode",
                        data={
                            "courseware_id": courseware.id,
                            "slide_no": slide.slide_no,
                            "exc_type": type(exc).__name__,
                            "error": self._sanitize_error_text(exc),
                        },
                    )
        else:
            pending_slides = iter(slides)
            future_map: dict = {}
            executor = ThreadPoolExecutor(max_workers=max_workers)
            try:
                for _ in range(max_workers):
                    try:
                        slide = next(pending_slides)
                    except StopIteration:
                        break
                    future_map[executor.submit(self._translate_single_slide, slide, term_hint)] = slide

                while future_map:
                    done, _ = wait(list(future_map.keys()), return_when=FIRST_COMPLETED)
                    for future in done:
                        slide = future_map.pop(future)
                        try:
                            _, translated_text, translated_layout, enhanced_source_text = future.result()
                            if self._mark_slide_translation_result(
                                slide,
                                translated_text,
                                translated_layout,
                                enhanced_source_text,
                            ):
                                translated_count += 1
                        except Exception as exc:
                            failed_slides.append((slide.slide_no, exc))
                            self._mark_slide_translation_failed(slide)
                            debug_log(
                                hypothesisId="H16",
                                runId="pre-diagnose",
                                location="translation_service:translate_courseware",
                                message="Single slide translation failed in parallel mode",
                                data={
                                    "courseware_id": courseware.id,
                                    "slide_no": slide.slide_no,
                                    "exc_type": type(exc).__name__,
                                    "error": self._sanitize_error_text(exc),
                                },
                            )

                        try:
                            next_slide = next(pending_slides)
                        except StopIteration:
                            continue
                        future_map[executor.submit(self._translate_single_slide, next_slide, term_hint)] = next_slide
            finally:
                executor.shutdown(wait=True, cancel_futures=True)

        if translated_count == 0:
            courseware.status = Courseware.STATUS_FAILED
        else:
            courseware.status = Courseware.STATUS_TRANSLATED

        courseware.last_error = self._build_failure_summary(failed_slides, len(slides))
        if started_at:
            courseware.translation_duration_seconds = max(
                int((timezone.now() - started_at).total_seconds()),
                0,
            )
        courseware.save(update_fields=["status", "last_error", "translation_duration_seconds", "updated_at"])
        return slides
