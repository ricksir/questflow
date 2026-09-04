from __future__ import annotations

"""Motor de conhecimento: RAG híbrido + grafo + índice semântico."""

from typing import Any


class KnowledgeEngine:
    engine_id = "knowledge_engine"
    name = "Knowledge Engine"
    version = "qf-knowledge-engine-3.4"

    def __init__(self, queries: Any, commands: Any):
        self.queries = queries
        self.commands = commands
        from pathlib import Path
        from core.multimodal_rag import MultimodalRetrievalRouter
        from core.retrieval_calibration import RetrievalCalibrationStore
        data_root = Path(__file__).resolve().parents[2] / "data" / "retrieval_quality"
        self.retrieval_calibration_store = RetrievalCalibrationStore(data_root)
        self.multimodal_router = MultimodalRetrievalRouter(queries, calibration_store=self.retrieval_calibration_store)

    def health(self) -> dict:
        summary = self.queries.semantic_index_summary()
        return {
            "id": self.engine_id,
            "name": self.name,
            "version": self.version,
            "status": "ready" if summary.get("offline_ready", True) else "degraded",
            "metrics": {
                "coverage": float(summary.get("coverage", 0) or 0),
                "rag_chunks": int(summary.get("rag_chunks", 0) or 0),
                "knowledge_nodes": int(summary.get("knowledge_nodes", 0) or 0),
                "knowledge_edges": int(summary.get("knowledge_edges", 0) or 0),
            },
        }

    def retrieve(self, uid: str, query: str = "", *, limit: int = 8) -> dict:
        return self.queries.rag_context(str(uid), str(query or ""), limit=max(1, min(20, int(limit))))

    def retrieve_multimodal(self, uid: str, query: str = "", *, limit: int = 8, backend: str = "hybrid") -> dict:
        return self.multimodal_router.retrieve(str(uid), str(query or ""), limit=limit, backend=backend)

    def retrieval_backends(self) -> list[dict]:
        return self.multimodal_router.catalog()

    def graph(self, uid: str) -> dict:
        return self.queries.knowledge_graph(str(uid))

    def summary(self) -> dict:
        return self.queries.semantic_index_summary()

    def observability_snapshot(self) -> dict:
        return self.queries.rag_observability_snapshot()

    def rebuild(self) -> dict:
        return self.commands.rebuild_semantic_index()

    def selected_sources(self, chunk_ids: list[str]) -> list[dict]:
        return self.queries.rag_chunks_by_ids(chunk_ids)
