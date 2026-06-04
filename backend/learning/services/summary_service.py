from __future__ import annotations

import json
import re

from learning.models import Courseware

from app.debug_logger import debug_log

from .llm_client import ChatMessage, OpenAICompatibleClient


class SummaryService:
    # 初始化当前对象需要的依赖和运行参数。
    def __init__(self):
        self.client = OpenAICompatibleClient()

    @staticmethod
    # 实现课件内容提取，把文本、位置和样式转成后续可用的结构。
    def _extract_json_payload(content: str) -> str:
        cleaned = (content or "").strip()
        if not cleaned:
            raise ValueError("Empty summary response.")

        # 总结模型偶尔会额外输出说明文字，这里只截取 JSON 主体，保证后续解析逻辑可控。
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
    # 实现课件总结和学习建议的数据整理，并提供可用的兜底结果。
    def _normalize_mind_map(node, fallback_title: str = "课程全景") -> dict:
        if not isinstance(node, dict):
            return {"title": fallback_title, "children": []}

        title = str(node.get("title", "")).strip() or fallback_title
        children = node.get("children", [])
        normalized_children = []
        if isinstance(children, list):
            for child in children[:12]:
                normalized_children.append(SummaryService._normalize_mind_map(child, "主题"))
        return {"title": title, "children": normalized_children}

    @staticmethod
    # 实现 _compact_text 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _compact_text(text: str, max_len: int = 96) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= max_len:
            return normalized
        return f"{normalized[:max_len].rstrip()}..."

    @staticmethod
    # 实现课件总结和学习建议的数据整理，并提供可用的兜底结果。
    def _normalize_suggestions(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = re.sub(r"\s+", " ", str(item or "")).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
            if len(normalized) >= 6:
                break
        return normalized

    @staticmethod
    # 实现课件总结和学习建议的数据整理，并提供可用的兜底结果。
    def build_learning_suggestions(
        chapter_summary: str,
        key_points: list[str] | None = None,
        term_pairs: list[dict] | None = None,
    ) -> list[str]:
        # 本地建议作为兜底路径存在：模型失败时仍能返回可用结果，而不是让整个总结接口失败。
        key_points = key_points or []
        term_pairs = term_pairs or []
        clean_points = [str(item or "").strip() for item in key_points if str(item or "").strip()]
        terms = [
            str(item.get("en", "")).strip()
            for item in term_pairs
            if isinstance(item, dict) and str(item.get("en", "")).strip()
        ]

        anchor = SummaryService._compact_text(chapter_summary, 54) if chapter_summary else "本课件核心内容"
        focus = SummaryService._compact_text(clean_points[0], 42) if clean_points else anchor
        suggestions: list[str] = [
            f"先用一句话回答“这节课到底想解决什么问题”：围绕“{focus}”写出问题、约束和结论，避免只背零散概念。",
            "学习时按“背景动机-核心机制-关键证据-应用边界”四栏整理笔记，每一栏只保留能解释因果关系的内容。",
            "做一次反向检查：假设某个关键条件不成立，推演结论会在哪一步失效，这能帮助你真正理解方法边界。",
        ]

        if terms:
            sampled_terms = "、".join(terms[:3])
            suggestions.append(
                f"把术语 {sampled_terms} 放进同一张关系图，标出它们分别回答“是什么、为什么、怎么用、何时失效”。"
            )
        else:
            point_count = max(len(clean_points), 1)
            suggestions.append(
                f"围绕 {point_count} 个关键点各设计一个自测问题，答案必须包含“现象、原因、适用条件、一个例子”。"
            )

        suggestions.append(f"复盘时不要重读全文，直接根据摘要“{anchor}”画出三条因果链，再回到课件查漏补缺。")
        return SummaryService._normalize_suggestions(suggestions)

    # 实现课件总结和学习建议的数据整理，并提供可用的兜底结果。
    def generate_learning_suggestions(
        self,
        chapter_summary: str,
        key_points: list[str] | None = None,
        term_pairs: list[dict] | None = None,
        mind_map: dict | None = None,
        courseware_title: str = "",
    ) -> list[str]:
        # 先生成本地 fallback，再尝试 LLM；这样任何异常都能退回到确定性结果。
        fallback = self.build_learning_suggestions(chapter_summary, key_points, term_pairs)
        payload = {
            "courseware_title": courseware_title,
            "chapter_summary": SummaryService._compact_text(chapter_summary, 1200),
            "key_points": (key_points or [])[:10],
            "term_pairs": (term_pairs or [])[:12],
            "mind_map": mind_map or {},
        }
        system_prompt = (
            "You are a senior bilingual course learning coach. "
            "Return strict JSON only. Do not include markdown."
        )
        user_prompt = (
            "基于下面的课件总结，为学生生成深入浅出的学习建议。\n"
            "输出格式必须是：{\"learning_suggestions\": [\"建议1\", \"建议2\"]}\n"
            "要求：\n"
            "1) 生成 5 条中文建议，每条 55-110 字。\n"
            "2) 每条都要包含具体做法，而不是空泛鼓励。\n"
            "3) 建议要围绕本课件内容，体现“为什么这样学、怎么操作、如何自检”。\n"
            "4) 避免套话，如认真学习、加强理解、做好笔记。\n"
            "5) 语言要像助教给学生的建议，深入但容易懂。\n\n"
            f"课件信息：\n{json.dumps(payload, ensure_ascii=False)}"
        )
        try:
            raw = self.client.chat(
                [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)],
                temperature=0.35,
            )
            parsed = json.loads(self._extract_json_payload(raw))
            suggestions = parsed.get("learning_suggestions", [])
            if isinstance(suggestions, list):
                normalized = self._normalize_suggestions([str(item) for item in suggestions])
                if normalized:
                    return normalized
        except Exception as exc:
            debug_log(
                hypothesisId="H18",
                runId="pre-diagnose",
                location="summary_service:generate_learning_suggestions",
                message="LLM learning suggestions failed, using local fallback",
                data={"exc_type": type(exc).__name__, "error": str(exc)[:500]},
            )
        return fallback

    @staticmethod
    # 实现数据规范化和结构构建，让调用方获得稳定的输出。
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

    # 实现 generate 对应的核心处理，封装输入转换、状态更新或结果返回。
    def generate(self, courseware: Courseware) -> tuple[str, list[str], list[dict], dict]:
        slides = list(courseware.slides.order_by("slide_no", "id"))
        corpus = []
        for slide in slides:
            # 优先使用译文参与总结；若尚未翻译完成，则退回原文，保证不同处理阶段都可用。
            text = (slide.translated_text or slide.source_text or "").strip()
            if text:
                corpus.append(f"[Slide {slide.slide_no}] {text}")
        content = "\n".join(corpus)
        if not content:
            return self._build_local_fallback(courseware, slides)

        system_prompt = (
            "You are a bilingual course summarization assistant. "
            "Return strict JSON with keys chapter_summary, key_points, term_pairs, mind_map. "
            "Build the mind_map as a conceptual knowledge map, not a slide-by-slide outline."
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
            "1) Root title should describe the whole courseware in Chinese.\n"
            "2) First-level nodes should be conceptual clusters such as background, core mechanism, method workflow, evidence, limitations, and application. Do not use page numbers as first-level nodes.\n"
            "3) Second-level nodes should explain relationships, causes, constraints, comparisons, or use cases rather than copying long source sentences.\n"
            "4) Keep tree depth within 3 levels, first-level node count within 4-8, and each node within 18 Chinese characters when possible.\n"
            "5) Prefer Chinese node titles. Keep English terms only when they are necessary technical terms.\n\n"
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
