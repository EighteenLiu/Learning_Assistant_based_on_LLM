from __future__ import annotations

import json
import re

from learning.models import Courseware

from app.debug_logger import debug_log

from .llm_client import ChatMessage, OpenAICompatibleClient


class SummaryService:
    def __init__(self):
        self.client = OpenAICompatibleClient()

    @staticmethod
    def _extract_json_payload(content: str) -> str:
        cleaned = (content or "").strip()
        if not cleaned:
            raise ValueError("Empty summary response.")

        fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", cleaned, flags=re.DOTALL)
        if fenced:
            return fenced.group(1).strip()

        first_object = cleaned.find("{")
        first_array = cleaned.find("[")
        candidates = [idx for idx in [first_object, first_array] if idx != -1]
        if not candidates:
            return cleaned

        start = min(candidates)
        end_object = cleaned.rfind("}")
        end_array = cleaned.rfind("]")
        end = max(end_object, end_array)
        if end >= start:
            return cleaned[start : end + 1].strip()
        return cleaned

    @staticmethod
    def _normalize_mind_map(node, fallback_title: str = "课程全景") -> dict:
        if not isinstance(node, dict):
            return {"title": fallback_title, "children": []}

        title = str(node.get("title", "")).strip() or fallback_title
        children = node.get("children", [])
        normalized_children = []
        if isinstance(children, list):
            for child in children[:8]:
                normalized_children.append(SummaryService._normalize_mind_map(child, "主题"))
        return {"title": title, "children": normalized_children}

    @staticmethod
    def _compact_text(text: str, max_len: int = 96) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= max_len:
            return normalized
        return f"{normalized[:max_len].rstrip()}..."

    @staticmethod
    def _normalize_suggestions(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
            if len(normalized) >= 5:
                break
        return normalized

    @staticmethod
    def build_learning_suggestions(
        chapter_summary: str,
        key_points: list[str] | None = None,
        term_pairs: list[dict] | None = None,
    ) -> list[str]:
        key_points = key_points or []
        term_pairs = term_pairs or []

        suggestions: list[str] = [
            "先把本章当作“系统设计问题”而不是“知识点列表”：核心不是记住步骤，而是识别每一步在防什么风险、约束什么行为、留下什么证据。",
            "从“规则”升级到“机制”理解：对每个关键结论都追问一次“如果去掉这条规则，系统最先失效在哪里”，你会看到知识背后的因果结构。",
            "把学习目标从“会复述”改成“会裁决”：给自己一个模糊案例，尝试在多种可行方案中做取舍并说明代价，这一步最能逼出真正理解。",
            "建立迁移能力：把本章方法套到另一个你熟悉的场景，检验哪些原则仍成立、哪些会失效；能迁移，才算掌握了抽象层能力。",
        ]

        terms = [
            str(item.get("en", "")).strip()
            for item in term_pairs
            if isinstance(item, dict) and str(item.get("en", "")).strip()
        ]
        if terms:
            sampled_terms = "、".join(terms[:3])
            suggestions.append(
                f"把术语 {sampled_terms} 放进同一个“概念关系图”：标出它们的前置条件、边界和冲突点，重点不是定义本身，而是它们如何共同决定决策质量。"
            )
        else:
            point_count = max(len([item for item in key_points if str(item).strip()]), 1)
            suggestions.append(
                f"围绕这 {point_count} 个关键点做一次“反例推演”：每个点都构造一个失败场景，写清楚失败触发条件和修正策略。"
            )

        summary_text = str(chapter_summary or "").strip()
        if summary_text:
            anchor = SummaryService._compact_text(summary_text, 36)
            suggestions.append(
                f"从摘要中的“{anchor}”抽出一句可执行判断准则，作为你后续做题或做项目时的决策锚点。"
            )

        return SummaryService._normalize_suggestions(suggestions)

    @staticmethod
    def _build_local_fallback(courseware: Courseware, slides: list, reason: str = "") -> tuple[str, list[str], list[dict], dict]:
        title = (courseware.title or "").strip() or "课程全景"
        key_points: list[str] = []
        seen: set[str] = set()
        children: list[dict] = []

        for slide in slides:
            slide_title = str(slide.title or "").strip() or f"第{slide.slide_no}页"
            source = (slide.translated_text or slide.source_text or "").strip()
            snippet = SummaryService._compact_text(source, 88) if source else ""
            point = f"{slide_title}：{snippet}" if snippet else slide_title
            if point not in seen:
                key_points.append(point)
                seen.add(point)
            if len(children) < 8:
                child = {"title": slide_title, "children": []}
                if snippet:
                    child["children"].append({"title": snippet, "children": []})
                children.append(child)
            if len(key_points) >= 8:
                break

        if not key_points:
            key_points = ["当前课件暂无可用于总结的文本内容。"]

        intro = "模型服务暂时不可用，已自动返回本地总结草稿。" if reason else "已生成本地总结草稿。"
        chapter_summary = f"{intro} 本课件共 {len(slides)} 页，建议先查看关键页后再重试 AI 总结以获得更完整结果。"
        mind_map = {"title": title, "children": children}
        return chapter_summary, key_points, [], mind_map

    def generate(self, courseware: Courseware) -> tuple[str, list[str], list[dict], dict]:
        slides = list(courseware.slides.order_by("slide_no", "id"))
        corpus = []
        for slide in slides:
            text = (slide.translated_text or slide.source_text or "").strip()
            if text:
                corpus.append(f"[Slide {slide.slide_no}] {text}")
        content = "\n".join(corpus)
        if not content:
            return self._build_local_fallback(courseware, slides)

        system_prompt = (
            "You are a bilingual course summarization assistant. "
            "Return strict JSON with keys chapter_summary, key_points, term_pairs, mind_map."
        )
        user_prompt = (
            "Please summarize the following courseware content.\n"
            "Output JSON format:\n"
            "{\n"
            '  "chapter_summary": "string",\n'
            '  "key_points": ["string"],\n'
            '  "term_pairs": [{"en": "string", "zh": "string"}],\n'
            '  "mind_map": {\n'
            '    "title": "string",\n'
            '    "children": [\n'
            '      {"title": "string", "children": [{"title": "string", "children": []}]}\n'
            "    ]\n"
            "  }\n"
            "}\n\n"
            "Mind map requirements:\n"
            "1) Root title should describe the whole courseware.\n"
            "2) Keep tree depth within 3 levels.\n"
            "3) Each node should be concise.\n\n"
            f"Course content:\n{content[:20000]}"
        )

        try:
            raw = self.client.chat(
                [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)],
                temperature=0.2,
            )
        except Exception as exc:
            debug_log(
                hypothesisId="H17",
                runId="pre-diagnose",
                location="summary_service:generate",
                message="LLM summary failed, using local fallback",
                data={
                    "courseware_id": courseware.id,
                    "exc_type": type(exc).__name__,
                    "error": str(exc)[:500],
                },
            )
            return self._build_local_fallback(courseware, slides, reason=str(exc))
        try:
            parsed = json.loads(self._extract_json_payload(raw))
            chapter_summary = str(parsed.get("chapter_summary", "")).strip()
            key_points = [str(item).strip() for item in parsed.get("key_points", []) if str(item).strip()]
            term_pairs = [
                {"en": str(item.get("en", "")).strip(), "zh": str(item.get("zh", "")).strip()}
                for item in parsed.get("term_pairs", [])
                if str(item.get("en", "")).strip() or str(item.get("zh", "")).strip()
            ]
            mind_map = self._normalize_mind_map(parsed.get("mind_map", {}), courseware.title or "课程全景")
            if not chapter_summary and not key_points:
                return self._build_local_fallback(courseware, slides, reason="empty_llm_summary")
            return chapter_summary, key_points, term_pairs, mind_map
        except (ValueError, TypeError, AttributeError):
            return raw.strip(), [], [], {"title": courseware.title or "课程全景", "children": []}
