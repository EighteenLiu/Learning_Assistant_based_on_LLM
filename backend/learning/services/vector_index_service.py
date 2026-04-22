from __future__ import annotations

import chromadb
from chromadb.config import Settings
from django.conf import settings

from app.debug_logger import debug_log


class VectorIndexService:
    def __init__(self):
        #region agent log H3_vector_init_attempt
        debug_log(
            hypothesisId="H3",
            runId="pre-diagnose",
            location="vector_index_service:__init__",
            message="Initializing Chroma PersistentClient",
            data={
                "persist_dir": settings.CHROMA_PERSIST_DIR,
                "collection": "courseware_slides",
            },
        )
        #endregion
        try:
            self.client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False),
            )
            self.collection = self.client.get_or_create_collection(name="courseware_slides")
        except Exception as exc:
            #region agent log H3_vector_init_exception
            debug_log(
                hypothesisId="H3",
                runId="pre-diagnose",
                location="vector_index_service:__init__",
                message="Chroma init failed",
                data={"exc_type": type(exc).__name__, "error": str(exc)[:500]},
            )
            #endregion
            raise

    @staticmethod
    def _doc_id(courseware_id: int, slide_no: int) -> str:
        return f"courseware-{courseware_id}-slide-{slide_no}"

    @staticmethod
    def _build_where(courseware_id: int, slide_no: int | None = None) -> dict:
        if slide_no is None:
            return {"courseware_id": courseware_id}
        return {"$and": [{"courseware_id": courseware_id}, {"slide_no": slide_no}]}

    def rebuild_courseware_index(self, courseware, slides):
        existing_ids = [self._doc_id(courseware.id, slide.slide_no) for slide in slides]
        if existing_ids:
            existing = self.collection.get(ids=existing_ids, include=[])
            persisted_ids = existing.get("ids", []) if isinstance(existing, dict) else []
            if persisted_ids:
                self.collection.delete(ids=persisted_ids)

        documents = []
        metadatas = []
        ids = []

        for slide in slides:
            content = (slide.translated_text or slide.source_text or "").strip()
            if not content:
                continue
            ids.append(self._doc_id(courseware.id, slide.slide_no))
            documents.append(content)
            metadatas.append(
                {
                    "courseware_id": courseware.id,
                    "slide_no": slide.slide_no,
                    "owner_id": courseware.owner_id,
                }
            )
        if ids:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)

    def query(self, courseware_id: int, question: str, top_k: int = 3, slide_no: int | None = None) -> list[dict]:
        results = self.collection.query(
            query_texts=[question],
            n_results=top_k,
            where=self._build_where(courseware_id, slide_no),
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        out: list[dict] = []
        for doc, meta, distance in zip(docs, metas, distances):
            out.append(
                {
                    "content": doc,
                    "slide_no": meta.get("slide_no"),
                    "score": float(distance) if distance is not None else None,
                }
            )
        return out
