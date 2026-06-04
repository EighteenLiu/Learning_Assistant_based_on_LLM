from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError
from django.db.models import F
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

    # 初始化当前对象需要的依赖和运行参数。
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
        self.chunk_max_retries = max(int(getattr(settings, "TRANSLATION_CHUNK_MAX_RETRIES", 2) or 1), 1)
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
    # 实现数据规范化和结构构建，让调用方获得稳定的输出。
    def _build_term_hint() -> str:
        terms = TermDictionary.objects.all()[:200]
        if not terms:
            return ""
        pairs = "\n".join([f"{term.source_term} => {term.target_term}" for term in terms])
        return f"Fixed terminology mappings:\n{pairs}"

    @staticmethod
    # 实现 _sha256 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _sha256(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    # 实现缓存读写和命中判断，用于减少重复模型请求。
    def _build_cache_key(self, text: str, term_hint: str, translation_type: str) -> str:
        source_text = (text or "").strip()
        term_hash = self._sha256((term_hint or "").strip())
        # 缓存维度包含 schema、类型、模型、语种、术语表和原文，确保换模型或改术语表时不会复用旧译文。
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

    # 实现缓存读写和命中判断，用于减少重复模型请求。
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

    # 实现缓存读写和命中判断，用于减少重复模型请求。
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

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
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

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
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
    # 实现课件内容提取，把文本、位置和样式转成后续可用的结构。
    def _extract_json_payload(content: str) -> str:
        cleaned = (content or "").strip()
        if not cleaned:
            raise ValueError("Empty translation response.")

        # LLM 有时会把 JSON 包在 markdown 代码块里；先剥离外壳，再做严格解析，提升接口稳定性。
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
    # 实现数据规范化和结构构建，让调用方获得稳定的输出。
    def _normalize_lines(lines: list[str]) -> list[str]:
        return [str(line).strip() for line in lines if str(line).strip()]

    @staticmethod
    # 实现 _resolve_media_path 对应的核心处理，封装输入转换、状态更新或结果返回。
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
    # 实现 _container_area_ratio 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _container_area_ratio(container: dict) -> float:
        width = max(float(container.get("w", 0) or 0), 0.0)
        height = max(float(container.get("h", 0) or 0), 0.0)
        return width * height

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
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

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
    def _extract_and_translate_image_region_text(self, image_data_url: str, term_hint: str) -> tuple[str, str]:
        system_prompt = (
            "You are an OCR + translation assistant for course slides. "
            "Extract visible text from the image region and translate only meaningful English course content into Simplified Chinese."
        )
        user_text = (
            f"{term_hint}\n\n"
            "Requirements:\n"
            "1) Extract only visible text in the image region.\n"
            "2) If the region contains three or more English words, translate the meaningful English content into Simplified Chinese even when it is mixed with numbers, symbols, formulas, or imperfect OCR fragments.\n"
            "3) If the region is a watermark, logo, icon, decorative image, chart/plot with no meaningful text to translate, "
            "or text is already mostly Simplified Chinese, return empty strings for both fields.\n"
            "4) Ignore pure numbers, axis ticks, isolated symbols, and non-knowledge fragments.\n"
            "5) Keep concise line structure when possible.\n"
            '6) Return strict JSON only: {"source_text": "...", "translated_text": "..."}.\n'
            "7) If no readable text should be translated, both fields should be empty string.\n"
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

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
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

        # 图片 OCR 成本高且容易误识别，优先处理面积较大的图片区域，并限制每页最多处理数量。
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
            # 图片区域缓存不能只看坐标，还要加裁剪后图片摘要；原图变化时缓存会自动失效。
            source_token = (
                f"imgocr:v3:{slide.id}:{container_id}:{image_digest}:"
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
            if not PPTParserService.should_keep_image_ocr_result(source_text, translated_text):
                continue
            translated_map[container_id] = {
                "text": translated_text,
                "paragraphs": self._normalize_lines(translated_text.splitlines()) or [translated_text],
            }
            if source_text:
                source_text_map[container_id] = source_text

        return translated_map, source_text_map

    @staticmethod
    # 实现 _split_to_match_paragraphs 对应的核心处理，封装输入转换、状态更新或结果返回。
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

    # 实现 _chunk_payload_containers 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _chunk_payload_containers(self, payload_containers: list[dict]) -> list[list[dict]]:
        if not payload_containers:
            return []

        # 按容器数量和字符数双阈值切块，既控制单次 LLM 请求大小，又尽量保留同页上下文。
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

    # 实现缓存读写和命中判断，用于减少重复模型请求。
    def _load_cached_containers(self, payload_containers: list[dict], term_hint: str) -> tuple[dict[int, dict], list[dict]]:
        if not payload_containers:
            return {}, []

        # 先批量查缓存，再只翻译未命中的容器；大课件里重复标题和术语很多，这一步能减少请求数。
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

    # 实现缓存读写和命中判断，用于减少重复模型请求。
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

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
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
    # 实现 _missing_payload_containers 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _missing_payload_containers(payload_containers: list[dict], translated_map: dict[int, dict]) -> list[dict]:
        missing: list[dict] = []
        for container in payload_containers:
            container_id = int(container.get("container_id") or 0)
            translated_text = str(translated_map.get(container_id, {}).get("text", "")).strip()
            if not translated_text:
                missing.append(container)
        return missing

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
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

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
    def _translate_container_chunk_with_retries(
        self,
        payload_containers: list[dict],
        term_hint: str,
        slide: SlideContent | None = None,
    ) -> dict[int, dict]:
        # 结构化翻译要求返回 container_id 和 paragraphs；失败后重试，避免一个坏响应影响整份课件。
        last_exc: Exception | None = None
        for attempt in range(1, self.chunk_max_retries + 1):
            try:
                return self._translate_container_chunk(payload_containers, term_hint)
            except Exception as exc:
                last_exc = exc
                debug_log(
                    hypothesisId="H18",
                    runId="pre-diagnose",
                    location="translation_service:_translate_container_chunk_with_retries",
                    message="Container chunk translation failed, retrying" if attempt < self.chunk_max_retries else "Container chunk translation failed finally",
                    data={
                        "courseware_id": getattr(getattr(slide, "courseware", None), "id", None),
                        "slide_no": getattr(slide, "slide_no", None),
                        "attempt": attempt,
                        "max_retries": self.chunk_max_retries,
                        "container_count": len(payload_containers),
                        "char_count": sum(len(str(item.get("text", ""))) for item in payload_containers),
                        "exc_type": type(exc).__name__,
                        "error": self._sanitize_error_text(exc),
                    },
                )
                if attempt < self.chunk_max_retries:
                    time.sleep(min(0.5 * attempt, 2.0))
        if last_exc is not None:
            raise last_exc
        return {}

    # 实现 _split_long_text_for_translation 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _split_long_text_for_translation(self, text: str) -> list[str]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        max_chars = max(self.chunk_max_chars, 200)
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
        if not paragraphs:
            paragraphs = [line.strip() for line in normalized.splitlines() if line.strip()] or [normalized]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if current:
                    chunks.append("\n\n".join(current).strip())
                    current = []
                    current_len = 0
                for start in range(0, len(paragraph), max_chars):
                    part = paragraph[start : start + max_chars].strip()
                    if part:
                        chunks.append(part)
                continue

            next_len = current_len + len(paragraph) + (2 if current else 0)
            if current and next_len > max_chars:
                chunks.append("\n\n".join(current).strip())
                current = [paragraph]
                current_len = len(paragraph)
            else:
                current.append(paragraph)
                current_len = next_len
        if current:
            chunks.append("\n\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
    def _translate_long_container_text(
        self,
        container: dict,
        term_hint: str,
        slide: SlideContent | None = None,
    ) -> dict:
        # 超长文本单独处理，避免因为一个大文本框导致整页结构化翻译超过模型上下文限制。
        source_text = str(container.get("text", "")).strip()
        chunks = self._split_long_text_for_translation(source_text)
        if not chunks:
            return {"text": "", "paragraphs": []}

        courseware_id = getattr(getattr(slide, "courseware", None), "id", None)
        slide_no = getattr(slide, "slide_no", None)
        self._add_translation_chunks(courseware_id, len(chunks), slide_no)

        translated_parts: list[str] = []
        for chunk in chunks:
            last_exc: Exception | None = None
            translated = ""
            for attempt in range(1, self.chunk_max_retries + 1):
                try:
                    translated = self._translate_text(
                        chunk,
                        term_hint,
                        translation_type=self.CACHE_TYPE_CONTAINER,
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    debug_log(
                        hypothesisId="H19",
                        runId="pre-diagnose",
                        location="translation_service:_translate_long_container_text",
                        message="Long container sub-chunk failed, retrying" if attempt < self.chunk_max_retries else "Long container sub-chunk failed finally",
                        data={
                            "courseware_id": courseware_id,
                            "slide_no": slide_no,
                            "attempt": attempt,
                            "max_retries": self.chunk_max_retries,
                            "char_count": len(chunk),
                            "exc_type": type(exc).__name__,
                            "error": self._sanitize_error_text(exc),
                        },
                    )
                    if attempt < self.chunk_max_retries:
                        time.sleep(min(0.5 * attempt, 2.0))
            if not translated and last_exc is not None:
                raise last_exc
            translated_parts.append(translated)
            self._mark_translation_chunk_done(courseware_id, slide_no)

        translated_text = "\n\n".join(part for part in translated_parts if str(part).strip()).strip()
        return {
            "text": translated_text,
            "paragraphs": self._split_to_match_paragraphs(
                translated_text,
                list(container.get("paragraphs", [])),
            ),
        }

    @staticmethod
    # 实现 _add_translation_chunks 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _add_translation_chunks(courseware_id: int | None, chunk_count: int, slide_no: int | None = None) -> None:
        if not courseware_id or chunk_count <= 0:
            return
        update_fields = {"translation_total_chunks": F("translation_total_chunks") + chunk_count}
        if slide_no:
            update_fields["translation_current_slide_no"] = slide_no
        try:
            Courseware.objects.filter(id=courseware_id).update(**update_fields)
        except DatabaseError:
            return

    @staticmethod
    # 实现 _mark_translation_chunk_done 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _mark_translation_chunk_done(courseware_id: int | None, slide_no: int | None = None) -> None:
        if not courseware_id:
            return
        # 用数据库 F 表达式做原子递增，多个翻译线程并发更新进度时不会互相覆盖。
        update_fields = {"translation_completed_chunks": F("translation_completed_chunks") + 1}
        if slide_no:
            update_fields["translation_current_slide_no"] = slide_no
        try:
            Courseware.objects.filter(id=courseware_id).update(**update_fields)
        except DatabaseError:
            return

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
    def _translate_containers(self, containers: list[dict], term_hint: str, slide: SlideContent | None = None) -> dict[int, dict]:
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

        # 普通容器走批量结构化翻译，超长容器拆成专门流程，兼顾吞吐量和模型上下文上限。
        normal_pending: list[dict] = []
        long_pending: list[dict] = []
        for container in pending_containers:
            if len(str(container.get("text", "") or "")) > self.chunk_max_chars:
                long_pending.append(container)
            else:
                normal_pending.append(container)

        for container in long_pending:
            container_id = int(container.get("container_id") or 0)
            if not container_id:
                continue
            translated_payload = self._translate_long_container_text(container, term_hint, slide=slide)
            translated_map[container_id] = translated_payload
            self._cache_container_results([container], {container_id: translated_payload}, term_hint)

        chunks = self._chunk_payload_containers(normal_pending)
        courseware_id = getattr(getattr(slide, "courseware", None), "id", None)
        slide_no = getattr(slide, "slide_no", None)
        self._add_translation_chunks(courseware_id, len(chunks), slide_no)
        for chunk in chunks:
            chunk_map = self._translate_container_chunk_with_retries(chunk, term_hint, slide=slide)
            translated_map.update(chunk_map)
            self._cache_container_results(chunk, chunk_map, term_hint)
            self._mark_translation_chunk_done(courseware_id, slide_no)
        return translated_map

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
    def _build_translated_layout(
        self,
        slide: SlideContent,
        term_hint: str,
        repeated_short_phrase_fingerprints: set[str] | None = None,
    ) -> tuple[str, dict, str]:
        source_layout = copy.deepcopy(slide.source_layout or {})
        source_containers = source_layout.get("text_containers", []) or []
        if not source_containers:
            # 兼容旧版本数据：早期只保存 blocks，没有 text_containers，这里转换成统一容器结构。
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
            # PDF 页眉页脚常被解析成每页重复短句，去重后可以减少无意义翻译和预览干扰。
            source_containers = PPTParserService.dedupe_pdf_repeated_short_phrases(source_containers)
        else:
            source_containers = PPTParserService.filter_ppt_translation_containers(
                source_containers,
                repeated_short_phrase_fingerprints=repeated_short_phrase_fingerprints,
            )

        text_containers = [item for item in source_containers if str(item.get("kind", "")) != "image_ocr"]
        image_containers = [item for item in source_containers if str(item.get("kind", "")) == "image_ocr"]

        # 文本框和图片内文字分两条链路处理，最后按 container_id 合并回同一个 translated_layout。
        translated_map = self._translate_containers(text_containers, term_hint, slide=slide)
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
            if not translated_text:
                continue
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
            # blocks 是给前端快速预览用的轻量结构；text_containers 保留导出时需要的原始形状信息。
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
            base_source_text = "\n".join(
                [
                    str(container.get("text", "")).strip()
                    for container in text_containers
                    if str(container.get("text", "")).strip()
                ]
            ).strip()
            if not base_source_text:
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
            # OCR 文本补进 source_text，后续总结和问答才能检索到图片里的知识点。
            ocr_block = "[Image OCR]\n" + "\n".join(deduped_ocr)
            enhanced_source_text = "\n\n".join([part for part in [base_source_text, ocr_block] if part]).strip()
        return "\n".join(translated_texts).strip(), translated_layout, enhanced_source_text

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
    def _translate_single_slide(
        self,
        slide: SlideContent,
        term_hint: str,
        repeated_short_phrase_fingerprints: set[str] | None = None,
    ) -> tuple[int, str, dict, str]:
        translated_text, translated_layout, enhanced_source_text = self._build_translated_layout(
            slide,
            term_hint,
            repeated_short_phrase_fingerprints=repeated_short_phrase_fingerprints,
        )
        return slide.id, translated_text, translated_layout, enhanced_source_text

    @staticmethod
    # 实现 _sanitize_error_text 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _sanitize_error_text(exc: Exception) -> str:
        return " ".join(str(exc).split())[:240]

    @staticmethod
    # 实现 _has_textual_source 对应的核心处理，封装输入转换、状态更新或结果返回。
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

    # 实现课件总结和学习建议的数据整理，并提供可用的兜底结果。
    def _build_failure_summary(self, failed_slides: list[tuple[int, Exception]], total: int) -> str:
        if not failed_slides:
            return ""
        first_slide_no, first_exc = failed_slides[0]
        first_error = self._sanitize_error_text(first_exc)
        return (
            f"共有 {len(failed_slides)}/{total} 页翻译失败。"
            f"首个失败页：第 {first_slide_no} 页。错误：{first_error}"
        )

    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _mark_slide_translation_result(
        self,
        slide: SlideContent,
        translated_text: str,
        translated_layout: dict,
        source_text: str,
    ) -> bool:
        has_source = self._has_textual_source(source_text, slide.source_layout or {})
        # 没有可翻译文本的图片页也标记完成，否则进度统计会误认为任务一直没结束。
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
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _mark_slide_translation_failed(slide: SlideContent) -> None:
        SlideContent.objects.filter(id=slide.id).update(translation_done=False)

    # 实现数据规范化和结构构建，让调用方获得稳定的输出。
    def build_processed_previews(self, courseware: Courseware, slides: list[SlideContent]) -> None:
        # 预览图是异步生成的派生产物，失败不影响 translated_layout 入库，用户仍可导出或重试。
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

    # 实现翻译处理步骤，负责组织输入、调用模型并整理译文结果。
    def translate_courseware(self, courseware: Courseware):
        term_hint = self._build_term_hint()
        slides = list(courseware.slides.order_by("slide_no", "id"))
        failed_slides: list[tuple[int, Exception]] = []
        translated_count = 0
        started_at = courseware.translation_started_at
        repeated_short_phrase_fingerprints: set[str] | None = None

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

        try:
            if PPTParserService.is_ppt_file(courseware.file.path):
                # PPT 中重复短句通常是页脚、版权或装饰文字，预先收集指纹后统一过滤。
                repeated_short_phrase_fingerprints = PPTParserService.collect_ppt_repeated_short_phrase_fingerprints(
                    [slide.source_layout or {} for slide in slides]
                )
        except Exception:
            repeated_short_phrase_fingerprints = None

        max_workers = min(self.max_workers, len(slides))
        if max_workers <= 1:
            # 单线程路径便于调试和低配置部署；并发数配置为 1 时不会走线程池。
            for slide in slides:
                try:
                    _, translated_text, translated_layout, enhanced_source_text = self._translate_single_slide(
                        slide,
                        term_hint,
                        repeated_short_phrase_fingerprints=repeated_short_phrase_fingerprints,
                    )
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
            # 采用滑动窗口式并发：始终保持最多 max_workers 个任务在跑，完成一页就补下一页。
            pending_slides = iter(slides)
            future_map: dict = {}
            executor = ThreadPoolExecutor(max_workers=max_workers)
            try:
                for _ in range(max_workers):
                    try:
                        slide = next(pending_slides)
                    except StopIteration:
                        break
                    future_map[
                        executor.submit(
                            self._translate_single_slide,
                            slide,
                            term_hint,
                            repeated_short_phrase_fingerprints,
                        )
                    ] = slide

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
                        future_map[
                            executor.submit(
                                self._translate_single_slide,
                                next_slide,
                                term_hint,
                                repeated_short_phrase_fingerprints,
                            )
                        ] = next_slide
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
