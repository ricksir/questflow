from __future__ import annotations

"""Fachadas de consulta e comando para o banco de questões.

A interface não precisa conhecer detalhes do SQLite nem misturar operações de
leitura e escrita. As fachadas mantêm compatibilidade com o repositório atual e
permitem substituir persistência ou adicionar auditoria sem alterar as telas.
"""

from pathlib import Path
from typing import Any

from .storage import QuestFlowDatabase
from .spreadsheet_taxonomy import SpreadsheetTaxonomy


class QuestionQueryService:
    def __init__(self, database: QuestFlowDatabase):
        self._database = database

    def stats(self) -> dict:
        return self._database.stats()

    def subjects(self) -> list[str]:
        return self._database.distinct_subjects()

    def lessons(self, subject: str = "") -> list[str]:
        return self._database.distinct_lessons(subject)

    def list(self, search: str = "", status: str = "todos", limit: int = 2000) -> list[dict]:
        return self._database.list_questions(search=search, status=status, limit=limit)

    def page(
        self,
        search: str = "",
        status: str = "todos",
        *,
        subject: str = "",
        lesson: str = "",
        offset: int = 0,
        limit: int = 500,
    ) -> tuple[int, list[dict]]:
        return self._database.list_questions_page(
            search=search,
            status=status,
            subject=subject,
            lesson=lesson,
            offset=offset,
            limit=limit,
        )

    def get(self, uid: str | None) -> dict | None:
        return self._database.get_question(str(uid)) if uid else None

    def all(self, *, approved_only: bool = False) -> list[dict]:
        return self._database.all_questions(approved_only=approved_only)

    def recent_imports(self, limit: int = 20) -> list[dict]:
        return self._database.recent_imports(limit=limit)

    def excluded_count(self, kind: str | None = None) -> int:
        return self._database.excluded_count(kind)

    def schema_history(self) -> list[dict]:
        return self._database.schema_history()

    def bank_intelligence_summary(self) -> dict:
        return self._database.bank_intelligence_summary()

    def refresh_bank_intelligence(self) -> dict:
        return self._database.rebuild_bank_intelligence_derived()

    def bank_intelligence_attention(self, kind: str, limit: int = 100) -> dict:
        return self._database.bank_intelligence_attention(kind, limit=limit)

    def question_intelligence(self, uid: str, *, scan_duplicates: bool = True) -> dict:
        return self._database.refresh_question_intelligence(uid, scan_duplicates=scan_duplicates)

    def semantic_index_summary(self) -> dict:
        return self._database.semantic_index_summary()

    def rag_observability_snapshot(self) -> dict:
        return self._database.rag_observability_snapshot()

    def knowledge_graph(self, uid: str) -> dict:
        return self._database.knowledge_graph_for_question(uid)

    def rag_context(self, uid: str, query: str = "", *, limit: int = 8) -> dict:
        return self._database.retrieve_rag_context(uid, query=query, limit=limit)

    def code_history(self, uid: str, limit: int = 50) -> list[dict]:
        return self._database.question_code_history(uid, limit=limit)

    def by_code(self, code: str) -> dict | None:
        return self._database.get_question_by_code(code)

    def legislation_versions(self, canonical_key: str = "", limit: int = 200) -> list[dict]:
        return self._database.list_legislation_versions(canonical_key, limit=limit)

    def resolve_legislation(self, canonical_key: str, reference_date: str) -> dict | None:
        return self._database.resolve_legislation_version(canonical_key, reference_date)

    def legislation_summary(self) -> dict:
        return self._database.temporal_legislation_summary()

    def rag_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        return self._database.rag_chunks_by_ids(chunk_ids)


class QuestionCommandService:
    def __init__(self, database: QuestFlowDatabase):
        self._database = database

    def import_extraction(self, result: dict) -> dict:
        return self._database.import_extraction(result)

    def update(self, uid: str, question: dict, *, change_source: str = "sistema") -> dict:
        return self._database.update_question(uid, question, change_source=change_source)

    def set_review_status(self, uid: str, status: str) -> None:
        self._database.set_review_status(uid, status)

    def complete_curation_review(self, uid: str, *, reviewer: str = "") -> dict:
        return self._database.complete_curation_review(uid, reviewer=reviewer)

    def archive(self, uid: str, *, kind: str = "anulada", reason: str = "") -> bool:
        return self._database.archive_question(uid, kind=kind, reason=reason)

    def delete(self, uid: str) -> None:
        self._database.delete_question(uid)

    def create_manual(self, taxonomy: SpreadsheetTaxonomy | None = None) -> str:
        return self._database.create_manual_question(taxonomy)

    def reclassify_all(self, taxonomy: SpreadsheetTaxonomy) -> dict:
        return self._database.reclassify_all(taxonomy)

    def organize_lesson_group(
        self,
        source_subject: str,
        source_lesson: str,
        target_subject: str,
        target_lesson: str,
        lesson_title: str,
    ) -> dict:
        return self._database.organize_lesson_group(
            source_subject,
            source_lesson,
            target_subject,
            target_lesson,
            lesson_title,
        )

    def import_database(self, source_path: str | Path) -> dict:
        return self._database.import_database(source_path)

    def resolve_duplicate_candidate(self, candidate_id: str, *, duplicate: bool = False) -> bool:
        return self._database.resolve_duplicate_candidate(candidate_id, duplicate=duplicate)

    def rebuild_semantic_index(self) -> dict:
        return self._database.rebuild_semantic_index()

    def upsert_legislation(self, payload: dict) -> dict:
        return self._database.upsert_legislation_version(payload)

    def backup(self, destination: str | Path) -> Path:
        return self._database.backup(destination)
