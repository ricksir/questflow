from __future__ import annotations

"""Projeto de Concurso/Edital — QuestFlow 6.5.

Mantém edital, retificações, conteúdo programático, vínculos com questões e
estado temporal. O serviço vive no Banco Editorial e fornece dados ao Learning
Engine sem criar um sétimo motor.
"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from .schema_migrations import apply_migration


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _norm(value: Any) -> str:
    text = str(value or "").casefold().strip()
    text = re.sub(r"[^a-z0-9áàâãéêíóôõúüç]+", " ", text)
    return " ".join(text.split())


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


CURRENCY_LABELS = {
    "vigente": "Vigente",
    "potencialmente_desatualizada": "Potencialmente desatualizada",
    "desatualizada": "Desatualizada",
    "anulada": "Anulada",
    "controversa": "Controversa",
    "historica": "Histórica",
}


@dataclass(slots=True)
class ExamProjectService:
    database: Any

    def __post_init__(self) -> None:
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.database.connect() as connection:
            def migration(conn):
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_exam_projects (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        agency TEXT,
                        role TEXT,
                        board TEXT,
                        exam_date TEXT,
                        status TEXT NOT NULL DEFAULT 'planejamento',
                        notes TEXT,
                        active INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_qf_exam_project_active
                        ON qf_exam_projects(active) WHERE active=1;

                    CREATE TABLE IF NOT EXISTS qf_exam_versions (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        version_no INTEGER NOT NULL,
                        label TEXT NOT NULL,
                        published_at TEXT,
                        effective_from TEXT,
                        source_label TEXT,
                        source_url TEXT,
                        content_text TEXT,
                        content_sha256 TEXT NOT NULL,
                        change_summary_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(project_id) REFERENCES qf_exam_projects(id) ON DELETE CASCADE,
                        UNIQUE(project_id, version_no)
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_exam_versions_project
                        ON qf_exam_versions(project_id, version_no DESC);

                    CREATE TABLE IF NOT EXISTS qf_exam_syllabus_items (
                        id TEXT PRIMARY KEY,
                        version_id TEXT NOT NULL,
                        parent_id TEXT,
                        ordinal INTEGER NOT NULL DEFAULT 0,
                        subject TEXT NOT NULL,
                        topic TEXT,
                        subtopic TEXT,
                        path TEXT NOT NULL,
                        weight REAL NOT NULL DEFAULT 1.0,
                        expected_questions INTEGER NOT NULL DEFAULT 0,
                        importance TEXT NOT NULL DEFAULT 'normal',
                        text_content TEXT,
                        active INTEGER NOT NULL DEFAULT 1,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        FOREIGN KEY(version_id) REFERENCES qf_exam_versions(id) ON DELETE CASCADE,
                        FOREIGN KEY(parent_id) REFERENCES qf_exam_syllabus_items(id) ON DELETE SET NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_exam_syllabus_version
                        ON qf_exam_syllabus_items(version_id, subject, ordinal);

                    CREATE TABLE IF NOT EXISTS qf_exam_question_links (
                        project_id TEXT NOT NULL,
                        syllabus_item_id TEXT NOT NULL,
                        question_uid TEXT NOT NULL,
                        match_method TEXT NOT NULL DEFAULT 'automatico',
                        confidence REAL NOT NULL DEFAULT 0.0,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(project_id, syllabus_item_id, question_uid),
                        FOREIGN KEY(project_id) REFERENCES qf_exam_projects(id) ON DELETE CASCADE,
                        FOREIGN KEY(syllabus_item_id) REFERENCES qf_exam_syllabus_items(id) ON DELETE CASCADE,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_exam_links_question
                        ON qf_exam_question_links(question_uid, active);

                    CREATE TABLE IF NOT EXISTS qf_question_currency (
                        question_uid TEXT PRIMARY KEY,
                        status TEXT NOT NULL DEFAULT 'vigente',
                        reference_date TEXT,
                        reason TEXT,
                        source_kind TEXT NOT NULL DEFAULT 'manual',
                        reviewed_at TEXT,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_question_currency_status
                        ON qf_question_currency(status, updated_at DESC);
                    """
                )
                now = _utc_now()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO qf_question_currency(question_uid,status,source_kind,updated_at)
                    SELECT uid,'vigente','migracao',? FROM questions
                    """,
                    (now,),
                )

            apply_migration(
                connection,
                component="question_bank",
                version=8,
                name="exam project edital versions syllabus coverage and temporal question status",
                callback=migration,
            )

    # ------------------------------ parsing ------------------------------
    @staticmethod
    def parse_syllabus_text(text: str) -> list[dict]:
        """Extrai uma estrutura editável de um edital colado.

        É deliberadamente conservador: não inventa pesos nem hierarquia. Aceita
        ``Matéria | Assunto | Peso | Questões`` e também ``MATÉRIA: a; b; c``.
        """
        output: list[dict] = []
        current_subject = ""
        ordinal = 0
        for raw in str(text or "").splitlines():
            line = re.sub(r"^\s*(?:[-•–—]|\d+(?:\.\d+)*[.)-]?)\s*", "", raw).strip()
            if not line:
                continue
            if "|" in line:
                parts = [part.strip() for part in line.split("|")]
                subject = parts[0] if parts else current_subject
                topic = parts[1] if len(parts) > 1 else ""
                weight = _safe_float(parts[2], 1.0) if len(parts) > 2 else 1.0
                expected = _safe_int(parts[3], 0) if len(parts) > 3 else 0
                ordinal += 1
                current_subject = subject or current_subject
                output.append({"ordinal": ordinal, "subject": subject or current_subject, "topic": topic, "weight": weight, "expected_questions": expected})
                continue
            if ":" in line:
                head, tail = [part.strip() for part in line.split(":", 1)]
                if head and len(head) <= 120:
                    current_subject = head
                    topics = [part.strip(" .") for part in re.split(r";(?=\s|$)", tail) if part.strip(" .")]
                    if topics:
                        for topic in topics:
                            ordinal += 1
                            output.append({"ordinal": ordinal, "subject": current_subject, "topic": topic, "weight": 1.0, "expected_questions": 0})
                    else:
                        ordinal += 1
                        output.append({"ordinal": ordinal, "subject": current_subject, "topic": "", "weight": 1.0, "expected_questions": 0})
                    continue
            looks_heading = line == line.upper() and len(line) <= 120 and len(line.split()) <= 12
            if looks_heading:
                current_subject = line.title()
                continue
            ordinal += 1
            output.append({"ordinal": ordinal, "subject": current_subject or "Conteúdo geral", "topic": line, "weight": 1.0, "expected_questions": 0})
        return output

    # ------------------------------ projetos -----------------------------
    def list_projects(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.*, (SELECT COUNT(*) FROM qf_exam_versions v WHERE v.project_id=p.id) AS version_count
                FROM qf_exam_projects p ORDER BY active DESC, updated_at DESC, name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def active_project(self) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM qf_exam_projects WHERE active=1 LIMIT 1").fetchone()
        return dict(row) if row else None

    def upsert_project(self, payload: dict) -> dict:
        project_id = str(payload.get("id") or uuid.uuid4())
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Informe um nome para o projeto de concurso.")
        exam_date = str(payload.get("exam_date") or "").strip() or None
        if exam_date:
            try:
                date.fromisoformat(exam_date)
            except ValueError as error:
                raise ValueError("Data da prova inválida; use AAAA-MM-DD.") from error
        now = _utc_now()
        active = 1 if bool(payload.get("active")) else 0
        with self.database.connect() as connection:
            if active:
                connection.execute("UPDATE qf_exam_projects SET active=0 WHERE active=1 AND id<>?", (project_id,))
            connection.execute(
                """
                INSERT INTO qf_exam_projects(id,name,agency,role,board,exam_date,status,notes,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,agency=excluded.agency,role=excluded.role,
                    board=excluded.board,exam_date=excluded.exam_date,status=excluded.status,notes=excluded.notes,
                    active=excluded.active,updated_at=excluded.updated_at
                """,
                (project_id, name, str(payload.get("agency") or ""), str(payload.get("role") or ""), str(payload.get("board") or ""),
                 exam_date, str(payload.get("status") or "planejamento"), str(payload.get("notes") or ""), active, now, now),
            )
            if not connection.execute("SELECT 1 FROM qf_exam_projects WHERE active=1 LIMIT 1").fetchone():
                connection.execute("UPDATE qf_exam_projects SET active=1 WHERE id=?", (project_id,))
            row = connection.execute("SELECT * FROM qf_exam_projects WHERE id=?", (project_id,)).fetchone()
        return dict(row)

    def set_active(self, project_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM qf_exam_projects WHERE id=?", (str(project_id),)).fetchone()
            if not row:
                raise ValueError("Projeto de concurso não encontrado.")
            connection.execute("UPDATE qf_exam_projects SET active=0")
            connection.execute("UPDATE qf_exam_projects SET active=1, updated_at=? WHERE id=?", (_utc_now(), str(project_id)))
        return self.project_dashboard(str(project_id))

    def _current_version_row(self, connection, project_id: str):
        return connection.execute(
            "SELECT * FROM qf_exam_versions WHERE project_id=? ORDER BY version_no DESC LIMIT 1", (str(project_id),)
        ).fetchone()

    def add_version(self, project_id: str, payload: dict) -> dict:
        project_id = str(project_id or "").strip()
        if not project_id:
            raise ValueError("Selecione um projeto de concurso.")
        content_text = str(payload.get("content_text") or payload.get("syllabus_text") or "").strip()
        raw_items = payload.get("items") if isinstance(payload.get("items"), list) else None
        items = [dict(item) for item in raw_items] if raw_items else self.parse_syllabus_text(content_text)
        if not items:
            raise ValueError("O edital precisa conter ao menos um item do conteúdo programático.")
        now = _utc_now()
        with self.database.connect() as connection:
            project = connection.execute("SELECT * FROM qf_exam_projects WHERE id=?", (project_id,)).fetchone()
            if not project:
                raise ValueError("Projeto de concurso não encontrado.")
            previous = self._current_version_row(connection, project_id)
            next_no = int(previous["version_no"] or 0) + 1 if previous else 1
            version_id = str(uuid.uuid4())
            normalized_content = content_text or "\n".join(f"{item.get('subject','')} | {item.get('topic','')}" for item in items)
            digest = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
            previous_items: list[dict] = []
            if previous:
                previous_items = [dict(row) for row in connection.execute("SELECT * FROM qf_exam_syllabus_items WHERE version_id=?", (previous["id"],)).fetchall()]
            diff = self._diff_items(previous_items, items)
            connection.execute(
                """
                INSERT INTO qf_exam_versions(id,project_id,version_no,label,published_at,effective_from,source_label,source_url,
                    content_text,content_sha256,change_summary_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (version_id, project_id, next_no, str(payload.get("label") or ("Edital inicial" if next_no == 1 else f"Retificação {next_no-1}")),
                 str(payload.get("published_at") or ""), str(payload.get("effective_from") or payload.get("published_at") or ""),
                 str(payload.get("source_label") or ""), str(payload.get("source_url") or ""), normalized_content, digest,
                 json.dumps(diff, ensure_ascii=False), now),
            )
            for index, item in enumerate(items, start=1):
                subject = str(item.get("subject") or "Conteúdo geral").strip()
                topic = str(item.get("topic") or "").strip()
                subtopic = str(item.get("subtopic") or "").strip()
                path = " > ".join(part for part in (subject, topic, subtopic) if part)
                connection.execute(
                    """
                    INSERT INTO qf_exam_syllabus_items(id,version_id,ordinal,subject,topic,subtopic,path,weight,expected_questions,
                        importance,text_content,active,metadata_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (str(uuid.uuid4()), version_id, _safe_int(item.get("ordinal"), index), subject, topic, subtopic, path,
                     max(0.05, _safe_float(item.get("weight"), 1.0)), max(0, _safe_int(item.get("expected_questions"), 0)),
                     str(item.get("importance") or "normal"), str(item.get("text_content") or topic or subtopic),
                     1, json.dumps(item.get("metadata") or {}, ensure_ascii=False)),
                )
            connection.execute("UPDATE qf_exam_projects SET updated_at=? WHERE id=?", (now, project_id))
        self.auto_link(project_id)
        self.scan_currency(project_id)
        return self.project_dashboard(project_id)

    @staticmethod
    def _diff_items(previous: list[dict], current: list[dict]) -> dict:
        def key(item: dict) -> str:
            return "|".join((_norm(item.get("subject")), _norm(item.get("topic")), _norm(item.get("subtopic"))))
        prev = {key(item): item for item in previous if key(item)}
        cur = {key(item): item for item in current if key(item)}
        added = sorted(set(cur) - set(prev))
        removed = sorted(set(prev) - set(cur))
        changed = []
        for item_key in sorted(set(prev) & set(cur)):
            old_w = _safe_float(prev[item_key].get("weight"), 1.0)
            new_w = _safe_float(cur[item_key].get("weight"), 1.0)
            old_q = _safe_int(prev[item_key].get("expected_questions"), 0)
            new_q = _safe_int(cur[item_key].get("expected_questions"), 0)
            if abs(old_w-new_w) > 1e-9 or old_q != new_q:
                changed.append({"key": item_key, "old_weight": old_w, "new_weight": new_w, "old_expected": old_q, "new_expected": new_q})
        return {"added": added, "removed": removed, "changed": changed, "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)}}

    # ------------------------- vínculos e cobertura ----------------------
    @staticmethod
    def _match_score(subject: str, topic: str, item_subject: str, item_topic: str) -> float:
        s1, s2 = _norm(subject), _norm(item_subject)
        t1, t2 = _norm(topic), _norm(item_topic)
        subject_score = 1.0 if s1 and s1 == s2 else SequenceMatcher(None, s1, s2).ratio() if s1 and s2 else 0.0
        if t2:
            if t1 == t2 and t1:
                topic_score = 1.0
            elif t1 and (t1 in t2 or t2 in t1):
                topic_score = 0.88
            else:
                topic_score = SequenceMatcher(None, t1, t2).ratio() if t1 and t2 else 0.0
            return 0.62 * subject_score + 0.38 * topic_score
        return 0.68 * subject_score

    def auto_link(self, project_id: str) -> dict:
        project_id = str(project_id or "").strip()
        with self.database.connect() as connection:
            current = self._current_version_row(connection, project_id)
            if not current:
                return {"linked": 0, "items": 0, "questions": 0}
            items = [dict(row) for row in connection.execute("SELECT * FROM qf_exam_syllabus_items WHERE version_id=? AND active=1", (current["id"],)).fetchall()]
            questions = [dict(row) for row in connection.execute("SELECT uid,subject,primary_topic,lesson FROM questions").fetchall()]
            item_ids = [item["id"] for item in items]
            if item_ids:
                placeholders = ",".join("?" for _ in item_ids)
                connection.execute(
                    f"DELETE FROM qf_exam_question_links WHERE project_id=? AND match_method='automatico' AND syllabus_item_id IN ({placeholders})",
                    [project_id, *item_ids],
                )
            now = _utc_now()
            linked = 0
            for question in questions:
                best_item = None
                best_score = 0.0
                qtopic = str(question.get("primary_topic") or question.get("lesson") or "")
                for item in items:
                    score = self._match_score(str(question.get("subject") or ""), qtopic, str(item.get("subject") or ""), str(item.get("topic") or ""))
                    if score > best_score:
                        best_score, best_item = score, item
                if best_item and best_score >= 0.66:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO qf_exam_question_links(project_id,syllabus_item_id,question_uid,match_method,confidence,active,created_at)
                        VALUES(?,?,?,?,?,?,?)
                        """,
                        (project_id, best_item["id"], question["uid"], "automatico", round(best_score, 4), 1, now),
                    )
                    linked += 1
        return {"linked": linked, "items": len(items), "questions": len(questions)}

    def _coverage_rows(self, connection, project_id: str, version_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT i.id,i.ordinal,i.subject,i.topic,i.subtopic,i.path,i.weight,i.expected_questions,i.importance,
                   COUNT(DISTINCT l.question_uid) AS linked_questions,
                   COALESCE(SUM(s.correct_count+s.wrong_count),0) AS attempts,
                   COALESCE(SUM(s.correct_count),0) AS correct,
                   AVG(CASE WHEN s.kt_mastery IS NOT NULL THEN s.kt_mastery END) AS mastery,
                   AVG(CASE WHEN s.kt_confidence IS NOT NULL THEN s.kt_confidence END) AS mastery_confidence,
                   COALESCE(SUM(CASE WHEN qc.status IN ('desatualizada','anulada','controversa') THEN 1 ELSE 0 END),0) AS restricted_questions
            FROM qf_exam_syllabus_items i
            LEFT JOIN qf_exam_question_links l ON l.syllabus_item_id=i.id AND l.project_id=? AND l.active=1
            LEFT JOIN study_state s ON s.question_uid=l.question_uid
            LEFT JOIN qf_question_currency qc ON qc.question_uid=l.question_uid
            WHERE i.version_id=? AND i.active=1
            GROUP BY i.id ORDER BY i.ordinal,i.subject,i.topic
            """,
            (project_id, version_id),
        ).fetchall()
        output=[]
        for row in rows:
            item=dict(row)
            attempts=int(item.get("attempts") or 0); correct=int(item.get("correct") or 0)
            item["accuracy"] = None if attempts <= 0 else round(correct/attempts, 4)
            item["mastery"] = None if item.get("mastery") is None else round(float(item["mastery"]), 4)
            item["mastery_confidence"] = round(float(item.get("mastery_confidence") or 0.0), 4)
            item["covered"] = int(item.get("linked_questions") or 0) > 0
            item["studied"] = attempts > 0
            item["mastered"] = bool((item["mastery"] is not None and item["mastery"] >= .70 and item["mastery_confidence"] >= .35) or (attempts >= 5 and (item["accuracy"] or 0) >= .75))
            gap = 1.0 if item["mastery"] is None else 1.0-float(item["mastery"])
            coverage_gap = 0.0 if item["covered"] else 1.0
            importance_mult = {"critica":1.35,"crítica":1.35,"alta":1.2,"normal":1.0,"baixa":.8}.get(_norm(item.get("importance")),1.0)
            item["priority"] = round(100*min(1.0, (0.48*gap+0.32*coverage_gap+0.20*(1.0-item["mastery_confidence"]))*importance_mult),1)
            output.append(item)
        return output

    def project_dashboard(self, project_id: str = "") -> dict:
        project_id = str(project_id or "").strip()
        with self.database.connect() as connection:
            project = connection.execute("SELECT * FROM qf_exam_projects WHERE id=?", (project_id,)).fetchone() if project_id else connection.execute("SELECT * FROM qf_exam_projects WHERE active=1 LIMIT 1").fetchone()
            if not project:
                return {"project": None, "projects": self.list_projects(), "version": None, "coverage": {}, "items": [], "diff": {}, "currency": self.currency_summary()}
            project=dict(project)
            current=self._current_version_row(connection, project["id"])
            if not current:
                return {"project": project, "projects": self.list_projects(), "version": None, "coverage": {"items":0,"covered":0,"studied":0,"mastered":0,"coverage_rate":0.0}, "items": [], "diff": {}, "currency": self.currency_summary()}
            current=dict(current)
            items=self._coverage_rows(connection, project["id"], current["id"])
            total=len(items); covered=sum(bool(i["covered"]) for i in items); studied=sum(bool(i["studied"]) for i in items); mastered=sum(bool(i["mastered"]) for i in items)
            total_weight=sum(float(i.get("weight") or 1.0) for i in items) or 1.0
            covered_weight=sum(float(i.get("weight") or 1.0) for i in items if i["covered"])
            mastered_weight=sum(float(i.get("weight") or 1.0) for i in items if i["mastered"])
            versions=[dict(row) for row in connection.execute("SELECT * FROM qf_exam_versions WHERE project_id=? ORDER BY version_no DESC", (project["id"],)).fetchall()]
        exam_date=str(project.get("exam_date") or "")
        days=None
        if exam_date:
            try: days=(date.fromisoformat(exam_date)-date.today()).days
            except ValueError: days=None
        diff=json.loads(current.get("change_summary_json") or "{}")
        return {
            "schema":"questflow.exam-project.v1", "project":project, "projects":self.list_projects(), "version":current,
            "versions":versions, "days_to_exam":days,
            "coverage":{"items":total,"covered":covered,"studied":studied,"mastered":mastered,"coverage_rate":round(covered/total,4) if total else 0.0,"study_rate":round(studied/total,4) if total else 0.0,"mastery_rate":round(mastered/total,4) if total else 0.0,"weighted_coverage":round(covered_weight/total_weight,4) if total else 0.0,"weighted_mastery":round(mastered_weight/total_weight,4) if total else 0.0},
            "items":sorted(items,key=lambda x:(-float(x.get("priority") or 0),int(x.get("ordinal") or 0))), "diff":diff,
            "currency":self.currency_summary(),
        }

    # ---------------------- atualidade das questões ----------------------
    def set_currency(self, question_uid: str, status: str, *, reason: str = "", reference_date: str = "", source_kind: str = "manual") -> dict:
        status=_norm(status).replace(" ","_")
        if status not in CURRENCY_LABELS:
            raise ValueError("Estado de atualidade inválido.")
        now=_utc_now()
        with self.database.connect() as connection:
            if not connection.execute("SELECT 1 FROM questions WHERE uid=?", (str(question_uid),)).fetchone():
                raise ValueError("Questão não encontrada.")
            connection.execute(
                """
                INSERT INTO qf_question_currency(question_uid,status,reference_date,reason,source_kind,reviewed_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(question_uid) DO UPDATE SET status=excluded.status,reference_date=excluded.reference_date,
                    reason=excluded.reason,source_kind=excluded.source_kind,reviewed_at=excluded.reviewed_at,updated_at=excluded.updated_at
                """,
                (str(question_uid),status,str(reference_date or ""),str(reason or ""),str(source_kind or "manual"),now,now),
            )
            row=connection.execute("SELECT * FROM qf_question_currency WHERE question_uid=?", (str(question_uid),)).fetchone()
        return dict(row)

    def scan_currency(self, project_id: str = "") -> dict:
        project_id=str(project_id or "").strip()
        project=self.project_dashboard(project_id).get("project") if project_id else self.active_project()
        exam_date=str((project or {}).get("exam_date") or date.today().isoformat())
        now=_utc_now(); flagged=0; scanned=0
        with self.database.connect() as connection:
            latest={}
            for row in connection.execute("SELECT canonical_key,MAX(effective_from) AS effective_from FROM qf_legislation_versions GROUP BY canonical_key").fetchall():
                latest[_norm(row["canonical_key"])]=str(row["effective_from"] or "")
            rows=connection.execute("SELECT uid,exam_year,law_refs_text FROM questions").fetchall()
            for row in rows:
                scanned+=1
                refs=_norm(row["law_refs_text"])
                if not refs:
                    continue
                matches=[(key,eff) for key,eff in latest.items() if key and (key in refs or refs in key)]
                if not matches:
                    continue
                newest=max(matches,key=lambda item:item[1])[1]
                year=_safe_int(row["exam_year"],0)
                historical_cutoff=f"{year}-12-31" if year else ""
                if newest and newest <= exam_date and historical_cutoff and historical_cutoff < newest:
                    existing=connection.execute("SELECT status,source_kind FROM qf_question_currency WHERE question_uid=?", (row["uid"],)).fetchone()
                    if existing and str(existing["source_kind"] or "") == "manual" and str(existing["status"] or "vigente") != "vigente":
                        continue
                    connection.execute(
                        """
                        INSERT INTO qf_question_currency(question_uid,status,reference_date,reason,source_kind,updated_at)
                        VALUES(?,?,?,?,?,?) ON CONFLICT(question_uid) DO UPDATE SET status=excluded.status,reference_date=excluded.reference_date,
                            reason=excluded.reason,source_kind=excluded.source_kind,updated_at=excluded.updated_at
                        """,
                        (row["uid"],"potencialmente_desatualizada",exam_date,f"Norma relacionada possui versão com vigência em {newest}, posterior ao ano da questão.","varredura_temporal",now),
                    ); flagged+=1
        return {"scanned":scanned,"flagged":flagged,"reference_date":exam_date,**self.currency_summary()}

    def question_currency(self, question_uid: str) -> dict:
        uid = str(question_uid or "").strip()
        if not uid:
            return {"status": "vigente", "label": CURRENCY_LABELS.get("vigente", "Vigente"), "reason": "", "reference_date": "", "source_kind": "default"}
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM qf_question_currency WHERE question_uid=? LIMIT 1",
                (uid,),
            ).fetchone()
        if not row:
            return {"question_uid": uid, "status": "vigente", "label": CURRENCY_LABELS.get("vigente", "Vigente"), "reason": "", "reference_date": "", "source_kind": "default"}
        item = dict(row)
        item["label"] = CURRENCY_LABELS.get(str(item.get("status") or "vigente"), str(item.get("status") or "Vigente"))
        return item

    def currency_summary(self) -> dict:
        with self.database.connect() as connection:
            rows=connection.execute("SELECT status,COUNT(*) AS total FROM qf_question_currency GROUP BY status").fetchall()
            items=connection.execute(
                """
                SELECT qc.*,q.source_code,q.subject,q.primary_topic,q.exam_year FROM qf_question_currency qc
                JOIN questions q ON q.uid=qc.question_uid
                WHERE qc.status<>'vigente' ORDER BY qc.updated_at DESC LIMIT 30
                """
            ).fetchall()
        counts={key:0 for key in CURRENCY_LABELS}
        for row in rows: counts[str(row["status"])]=int(row["total"] or 0)
        return {"counts":counts,"labels":CURRENCY_LABELS,"attention":sum(counts.get(k,0) for k in ("potencialmente_desatualizada","desatualizada","anulada","controversa")),"items":[dict(row) for row in items]}
