from __future__ import annotations

"""Motor editorial do QuestFlow.

Fronteira responsável por questões, proveniência, curadoria e qualidade.
A camada web não deve precisar conhecer o SQLite nem detalhes das fachadas.
"""

from typing import Any


class EditorialBankEngine:
    engine_id = "editorial_bank"
    name = "Banco Editorial"
    version = "qf-editorial-engine-3"

    def __init__(self, queries: Any, commands: Any, database: Any | None = None):
        self.queries = queries
        self.commands = commands
        self.database = database
        self.exam_projects = None
        if database is not None:
            from ..exam_projects import ExamProjectService
            self.exam_projects = ExamProjectService(database)

    def health(self) -> dict:
        summary = self.queries.bank_intelligence_summary()
        legislation = self.queries.legislation_summary()
        return {
            "id": self.engine_id,
            "name": self.name,
            "version": self.version,
            "status": "ready",
            "metrics": {
                "questions": int(summary.get("total", 0) or 0),
                "average_quality": float(summary.get("average_quality", 0) or 0),
                "ready": int(summary.get("ready", 0) or 0),
                "legislation_versions": int(legislation.get("versions", 0) or 0),
                "temporal_norms": int(legislation.get("canonical_norms", 0) or 0),
                "exam_projects": len(self.exam_projects.list_projects()) if self.exam_projects else 0,
                "active_exam_project": bool(self.exam_projects.active_project()) if self.exam_projects else False,
            },
        }

    def question(self, uid: str) -> dict:
        question = self.queries.get(str(uid))
        if not question:
            raise ValueError("Questão não encontrada.")
        return question

    def intelligence(self, uid: str, *, scan_duplicates: bool = False) -> dict:
        result = self.queries.question_intelligence(str(uid), scan_duplicates=scan_duplicates)
        if self.exam_projects is not None:
            result["currency"] = self.exam_projects.question_currency(str(uid))
        return result

    def summary(self) -> dict:
        return self.queries.bank_intelligence_summary()

    def refresh_summary(self) -> dict:
        return self.queries.refresh_bank_intelligence()

    def attention(self, kind: str, *, limit: int = 100) -> dict:
        return self.queries.bank_intelligence_attention(kind, limit=limit)

    def complete_review(self, uid: str, *, reviewer: str = "") -> dict:
        return self.commands.complete_curation_review(str(uid), reviewer=str(reviewer or ""))

    def resolve_duplicate(self, candidate_id: str, *, duplicate: bool = False) -> bool:
        return bool(self.commands.resolve_duplicate_candidate(str(candidate_id), duplicate=bool(duplicate)))


    def question_candidates(self, limit: int = 60) -> list[dict]:
        return self.queries.list(limit=max(1, min(200, int(limit))))

    def legislation_versions(self, canonical_key: str = "", limit: int = 200) -> list[dict]:
        return self.queries.legislation_versions(str(canonical_key or ""), limit=limit)

    def resolve_legislation(self, canonical_key: str, reference_date: str) -> dict | None:
        return self.queries.resolve_legislation(str(canonical_key or ""), str(reference_date or ""))

    def upsert_legislation(self, payload: dict) -> dict:
        return self.commands.upsert_legislation(payload)

    def legislation_summary(self) -> dict:
        return self.queries.legislation_summary()

    def publish_generated_question(self, question: dict) -> dict:
        result = self.commands.import_extraction({
            "source_file": "QuestFlow Generator",
            "source_path": "",
            "questions": [question],
            "metadata": {"origin": "stage5_controlled_generation"},
        })
        code = str(question.get("codigo_origem") or question.get("id") or "")
        saved = self.queries.by_code(code)
        if not saved:
            raise ValueError("A questão gerada não pôde ser localizada após a publicação.")
        return {"import": result, "question": saved, "uid": str(saved.get("database_uid") or "")}


    # ------------------ Projeto de Concurso/Edital 6.5 ------------------
    def exam_project_dashboard(self, project_id: str = "") -> dict:
        if self.exam_projects is None:
            return {"project": None, "projects": [], "coverage": {}, "items": []}
        return self.exam_projects.project_dashboard(project_id)

    def upsert_exam_project(self, payload: dict) -> dict:
        if self.exam_projects is None:
            raise RuntimeError("Serviço de projetos de concurso indisponível.")
        return self.exam_projects.upsert_project(payload)

    def set_active_exam_project(self, project_id: str) -> dict:
        if self.exam_projects is None:
            raise RuntimeError("Serviço de projetos de concurso indisponível.")
        return self.exam_projects.set_active(project_id)

    def add_exam_version(self, project_id: str, payload: dict) -> dict:
        if self.exam_projects is None:
            raise RuntimeError("Serviço de projetos de concurso indisponível.")
        return self.exam_projects.add_version(project_id, payload)

    def parse_syllabus_text(self, text: str) -> list[dict]:
        if self.exam_projects is None:
            return []
        return self.exam_projects.parse_syllabus_text(text)

    def auto_link_exam_project(self, project_id: str) -> dict:
        if self.exam_projects is None:
            raise RuntimeError("Serviço de projetos de concurso indisponível.")
        return self.exam_projects.auto_link(project_id)

    def scan_question_currency(self, project_id: str = "") -> dict:
        if self.exam_projects is None:
            raise RuntimeError("Serviço de projetos de concurso indisponível.")
        return self.exam_projects.scan_currency(project_id)

    def set_question_currency(self, uid: str, status: str, *, reason: str = "", reference_date: str = "") -> dict:
        if self.exam_projects is None:
            raise RuntimeError("Serviço de projetos de concurso indisponível.")
        return self.exam_projects.set_currency(uid, status, reason=reason, reference_date=reference_date)
