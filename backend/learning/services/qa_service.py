from __future__ import annotations

from learning.models import Courseware

from .llm_client import ChatMessage, OpenAICompatibleClient
from .vector_index_service import VectorIndexService


class QAService:
    # 初始化当前对象需要的依赖和运行参数。
    def __init__(self):
        self.client = OpenAICompatibleClient()
        self.index_service = VectorIndexService()

    @staticmethod
    # 实现课件预览或导出处理，把布局数据转换为可视化结果。
    def _slide_payload(slide) -> str:
        parts = []
        title = (slide.title or "").strip()
        body = (slide.translated_text or slide.source_text or "").strip()
        notes = (slide.notes or "").strip()
        if title:
            parts.append(f"标题：{title}")
        if body:
            parts.append(body)
        if notes:
            parts.append(f"备注：{notes}")
        return "\n".join(parts).strip()

    @staticmethod
    # 实现数据规范化和结构构建，让调用方获得稳定的输出。
    def _build_history_text(history: list[dict]) -> str:
        lines: list[str] = []
        for item in history:
            role = item.get("role")
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            speaker = "学生" if role == "user" else "助教"
            lines.append(f"{speaker}：{content}")
        return "\n".join(lines).strip()

    # 实现问答上下文构建和结果整理，保证回答与课件内容关联。
    def _build_page_context(self, courseware: Courseware, question: str, slide_no: int) -> tuple[str, list[dict]]:
        current_slide = courseware.slides.filter(slide_no=slide_no).first()
        context_parts: list[str] = []
        citations: list[dict] = []
        seen_slide_nos: set[int] = set()

        if current_slide:
            # 当前页问答先放入当前页完整内容，保证回答不会偏离用户正在看的页面。
            payload = self._slide_payload(current_slide)
            if payload:
                context_parts.append(f"[当前页 {current_slide.slide_no}]\n{payload}")
                citations.append({"slide_no": current_slide.slide_no, "snippet": payload[:240]})
                seen_slide_nos.add(current_slide.slide_no)

        # 再补充少量相似页，解决概念跨页展开时“只看当前页信息不足”的问题。
        related_hits = self.index_service.query(courseware.id, question, top_k=3)
        for hit in related_hits:
            hit_slide_no = int(hit.get("slide_no") or 0)
            if not hit_slide_no or hit_slide_no in seen_slide_nos:
                continue
            context_parts.append(f"[相关页 {hit_slide_no}]\n{hit['content']}")
            citations.append({"slide_no": hit_slide_no, "snippet": hit["content"][:240]})
            seen_slide_nos.add(hit_slide_no)

        if not context_parts:
            context_parts.append("未检索到可用课件上下文。")
        return "\n\n".join(context_parts), citations

    # 实现问答上下文构建和结果整理，保证回答与课件内容关联。
    def _build_courseware_context(self, courseware: Courseware, question: str) -> tuple[str, list[dict]]:
        slides = list(courseware.slides.all())
        compiled: list[str] = []
        total_length = 0

        for slide in slides:
            # 全局问答尽量拼接整份课件，但设置长度上限，避免超过模型上下文窗口。
            payload = self._slide_payload(slide)
            if not payload:
                continue
            chunk = f"[第 {slide.slide_no} 页]\n{payload}"
            if total_length + len(chunk) > 22000 and compiled:
                break
            compiled.append(chunk)
            total_length += len(chunk)

        # 引用页码来自向量检索结果，答案可以整体阅读，引用则保持可追踪。
        hits = self.index_service.query(courseware.id, question, top_k=5)
        citations = [{"slide_no": hit["slide_no"], "snippet": hit["content"][:240]} for hit in hits]
        context = "\n\n".join(compiled) or "未检索到可用课件上下文。"
        return context, citations

    # 实现问答上下文构建和结果整理，保证回答与课件内容关联。
    def ask(
        self,
        courseware: Courseware,
        question: str,
        slide_no: int | None = None,
        use_global_scope: bool = False,
        history: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        history = history or []
        if use_global_scope:
            context, citations = self._build_courseware_context(courseware, question)
            scope_instruction = "本次问题基于整份 PPT，需要时可以综合多页内容作答。"
        else:
            context, citations = self._build_page_context(courseware, question, int(slide_no or 0))
            scope_instruction = "本次问题优先基于当前页回答，可引用相关页作为补充。"

        history_text = self._build_history_text(history)

        system_prompt = "你是一名双语课程助教。请使用简体中文回答，并严格基于提供的课件上下文作答。"
        user_prompt = (
            f"当前问题：\n{question}\n\n"
            f"回答范围：\n{scope_instruction}\n\n"
            f"历史对话：\n{history_text or '无'}\n\n"
            f"课件上下文：\n{context}\n\n"
            "回答规则：\n"
            "1) 仅根据课件上下文和历史对话回答。\n"
            "2) 如果上下文不足，请明确说明缺少哪些信息。\n"
            "3) 回答要清晰、简洁、适合教学场景。\n"
            "4) 如果有帮助，请自然提到页码。\n"
        )
        answer = self.client.chat(
            [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)],
            temperature=0.2,
        )
        return answer, citations
