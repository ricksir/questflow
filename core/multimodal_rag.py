from __future__ import annotations

"""QuestFlow 6.8.0 · Multimodal RAG 3.0.

This module keeps retrieval provider-neutral. Binary media never leaves the
computer here: it produces grounded local evidence plus a media descriptor.
The AI Gateway may only attach the binary when the privacy policy explicitly
allows it and the caller requests external multimodal use.
"""

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


MULTIMODAL_RAG_VERSION = "qf-multimodal-rag-3"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def _safe_path_metadata(path_value: str) -> dict:
    path = Path(str(path_value or "")) if str(path_value or "").strip() else None
    if path is None:
        return {"exists": False, "name": "", "suffix": "", "mime_type": "", "size_bytes": 0, "path_sha256": ""}
    exists = path.exists() and path.is_file()
    size = 0
    try:
        size = int(path.stat().st_size) if exists else 0
    except OSError:
        size = 0
    mime, _ = mimetypes.guess_type(path.name)
    return {
        "exists": exists,
        "name": path.name,
        "suffix": path.suffix.lower(),
        "mime_type": str(mime or "application/octet-stream"),
        "size_bytes": size,
        # Never expose the absolute local path in UI/audit payloads.
        "path_sha256": _sha256_text(str(path.resolve()) if exists else str(path)),
    }


@dataclass(slots=True)
class RetrievalContext:
    uid: str
    query: str
    question: dict
    limit: int


class RetrievalBackend(Protocol):
    backend_id: str
    modality: str

    def retrieve(self, context: RetrievalContext) -> list[dict]: ...


class LocalTextRagBackend:
    backend_id = "local_text_rag"
    modality = "text"

    def __init__(self, queries: Any):
        self.queries = queries

    def retrieve(self, context: RetrievalContext) -> list[dict]:
        raw = self.queries.rag_context(context.uid, context.query, limit=context.limit)
        items: list[dict] = []
        for item in raw.get("items", []) if isinstance(raw, dict) else []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            items.append({
                **item,
                "modality": "text",
                "backend": self.backend_id,
                "grounding": {
                    "version": MULTIMODAL_RAG_VERSION,
                    "question_uid": context.uid,
                    "source_kind": "rag_chunk",
                    "source_id": str(item.get("chunk_id") or item.get("id") or ""),
                    "content_sha256": _sha256_text(content),
                    "external_binary_shared": False,
                },
            })
        return items[: context.limit]


class LocalVisualEvidenceBackend:
    backend_id = "local_visual_evidence"
    modality = "visual"

    def retrieve(self, context: RetrievalContext) -> list[dict]:
        q = context.question or {}
        visual = q.get("contexto_visual") if isinstance(q.get("contexto_visual"), dict) else {}
        image = q.get("imagem_questao") if isinstance(q.get("imagem_questao"), dict) else {}
        image_path = str(image.get("path") or "").strip()
        image_meta = _safe_path_metadata(image_path)
        source_file = str(q.get("source_file") or "").strip()
        source_meta = _safe_path_metadata(source_file)

        parts: list[str] = []
        for key in ("descricao", "transcricao", "ocr", "texto", "observacao", "legenda"):
            value = visual.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(f"{key.replace('_', ' ').title()}: {value.strip()}")
        for key in ("paginas", "tipo", "origem", "imagem_extraida"):
            value = visual.get(key)
            if value not in (None, "", [], {}):
                parts.append(f"{key.replace('_', ' ').title()}: {value}")
        if image_meta["exists"]:
            parts.append(
                f"Imagem associada: {image_meta['name']} ({image_meta['mime_type']}, {image_meta['size_bytes']} bytes)."
            )
        if source_meta["exists"]:
            page = q.get("source_page") or image.get("page") or visual.get("paginas")
            parts.append(f"Documento de origem: {source_meta['name']}" + (f" · página {page}." if page else "."))
        if not parts:
            return []

        content = "\n".join(parts)[:5000]
        media_descriptors: list[dict] = []
        if image_meta["exists"]:
            media_descriptors.append({"kind": "image", **image_meta})
        if source_meta["exists"] and source_meta["suffix"] == ".pdf":
            media_descriptors.append({"kind": "pdf", **source_meta})
        return [{
            "title": "Evidência visual local da questão",
            "content": content,
            "scores": {"score": 1.0},
            "modality": "visual",
            "backend": self.backend_id,
            "media": media_descriptors,
            "grounding": {
                "version": MULTIMODAL_RAG_VERSION,
                "question_uid": context.uid,
                "source_kind": "question_visual_context",
                "source_page": q.get("source_page") or image.get("page") or None,
                "content_sha256": _sha256_text(content),
                "image_path_sha256": image_meta.get("path_sha256", ""),
                "source_path_sha256": source_meta.get("path_sha256", ""),
                "external_binary_shared": False,
            },
        }]


class MultimodalRetrievalRouter:
    """Interchangeable local retrieval backends with auditable calibrated fusion."""

    def __init__(self, queries: Any, calibration_store: Any | None = None):
        self.queries = queries
        self.calibration_store = calibration_store
        self.backends: dict[str, RetrievalBackend] = {
            "text": LocalTextRagBackend(queries),
            "visual": LocalVisualEvidenceBackend(),
        }

    def catalog(self) -> list[dict]:
        return [
            {"id": key, "backend": backend.backend_id, "modality": backend.modality, "local": True}
            for key, backend in self.backends.items()
        ]

    def retrieve(self, uid: str, query: str = "", *, limit: int = 8, backend: str = "hybrid") -> dict:
        question = self.queries.get(str(uid)) or {}
        limit = max(1, min(20, int(limit or 8)))
        context = RetrievalContext(uid=str(uid), query=str(query or ""), question=question, limit=limit)
        requested = str(backend or "hybrid").casefold()
        if requested not in {"hybrid", "text", "visual"}:
            requested = "hybrid"
        selected = ["text", "visual"] if requested == "hybrid" else [requested]
        items: list[dict] = []
        backend_errors: list[dict] = []
        for key in selected:
            try:
                items.extend(self.backends[key].retrieve(context))
            except Exception as error:  # retrieval must degrade per backend, not globally
                backend_errors.append({"backend": key, "error": str(error)})
        reranking_meta = None
        if requested == "hybrid":
            from core.retrieval_calibration import DEFAULT_PROFILE, rerank_items
            profile = self.calibration_store.current() if self.calibration_store is not None else DEFAULT_PROFILE
            items = rerank_items(items, query=context.query, question=question, profile=profile)
            reranking_meta = {"profile_id": profile.get("id"), "weights": profile.get("weights"), "version": "qf-retrieval-calibration-1"}
        else:
            items.sort(key=lambda item: -float((item.get("scores") or {}).get("score", item.get("score", 0)) or 0))
        fused = items[:limit]
        return {
            "engine": MULTIMODAL_RAG_VERSION,
            "backend": requested,
            "backend_catalog": self.catalog(),
            "reranking": reranking_meta,
            "items": fused,
            "modalities": sorted({str(item.get("modality") or "text") for item in fused}),
            "grounded_items": sum(1 for item in fused if isinstance(item.get("grounding"), dict)),
            "errors": backend_errors,
            "external_binary_shared": False,
        }


def media_paths_for_question(question: dict) -> list[dict]:
    """Returns local media paths only for the trusted local caller.

    Do not place this output in telemetry, audit logs or UI. It is intentionally
    separated from the retrieval descriptors which contain only path hashes.
    """
    out: list[dict] = []
    image = question.get("imagem_questao") if isinstance(question.get("imagem_questao"), dict) else {}
    image_path = str(image.get("path") or "").strip()
    if image_path and Path(image_path).is_file():
        meta = _safe_path_metadata(image_path)
        out.append({"kind": "image", "path": image_path, "mime_type": meta["mime_type"], "size_bytes": meta["size_bytes"]})
    source_file = str(question.get("source_file") or "").strip()
    if source_file and Path(source_file).is_file() and Path(source_file).suffix.lower() == ".pdf":
        meta = _safe_path_metadata(source_file)
        out.append({"kind": "pdf", "path": source_file, "mime_type": "application/pdf", "size_bytes": meta["size_bytes"]})
    return out


__all__ = [
    "MULTIMODAL_RAG_VERSION",
    "MultimodalRetrievalRouter",
    "media_paths_for_question",
]
