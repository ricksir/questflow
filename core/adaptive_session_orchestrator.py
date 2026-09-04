from __future__ import annotations

"""Adaptive Session Orchestrator — QuestFlow 6.14.1.

Camada de sessão sobre o ``StudyBatchService``. O orquestrador não substitui FSRS,
KT, IRT ou o Learner Model: ele usa a decisão do Core e replaneja a composição em
micro-lotes curtos conforme novas evidências chegam durante a sessão.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
import uuid
from typing import Any, Iterable

from .study_batch_service import StudyBatchService

ORCHESTRATOR_VERSION = "adaptive-session-orchestrator-v1"
DEFAULT_MICRO_BATCH_SIZE = 3
MAX_MICRO_BATCH_SIZE = 5


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _safe_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _topic_key(subject: Any, topic: Any, lesson: Any = "") -> tuple[str, str, str]:
    return (_norm(subject), _norm(topic), _norm(lesson))


@dataclass(slots=True)
class SessionEvidence:
    answered: int = 0
    correct: int = 0
    wrong: int = 0
    skipped: int = 0
    high_confidence_wrong: int = 0
    uncertain_correct: int = 0
    learning_gaps: int = 0
    focus_topics: list[dict[str, str]] | None = None
    last_question_uid: str = ""

    @property
    def accuracy(self) -> float | None:
        return None if self.answered <= 0 else self.correct / self.answered

    def to_dict(self) -> dict[str, Any]:
        return {
            "answered": self.answered,
            "correct": self.correct,
            "wrong": self.wrong,
            "skipped": self.skipped,
            "accuracy": None if self.accuracy is None else round(self.accuracy, 4),
            "high_confidence_wrong": self.high_confidence_wrong,
            "uncertain_correct": self.uncertain_correct,
            "learning_gaps": self.learning_gaps,
            "focus_topics": list(self.focus_topics or []),
            "last_question_uid": self.last_question_uid,
        }


class AdaptiveSessionOrchestrator:
    """Replaneja sessões em micro-lotes sem duplicar a inteligência do Learning Engine."""

    def __init__(self, database: Any, study_batch: StudyBatchService):
        self.database = database
        self.study_batch = study_batch
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS qf_adaptive_sessions (
                    session_id TEXT PRIMARY KEY,
                    learner_id TEXT,
                    device_id TEXT,
                    exam_project_id TEXT,
                    mode TEXT NOT NULL,
                    subject TEXT,
                    target_questions INTEGER NOT NULL,
                    micro_batch_size INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    strategy_profile TEXT NOT NULL DEFAULT 'balanced',
                    plan_revision INTEGER NOT NULL DEFAULT 0,
                    goal_json TEXT NOT NULL DEFAULT '{}',
                    state_signature TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_qf_adaptive_sessions_learner
                    ON qf_adaptive_sessions(learner_id,status,updated_at DESC);

                CREATE TABLE IF NOT EXISTS qf_adaptive_microbatches (
                    batch_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    plan_revision INTEGER NOT NULL,
                    purpose TEXT NOT NULL DEFAULT 'active',
                    status TEXT NOT NULL DEFAULT 'active',
                    strategy_profile TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    question_ids_json TEXT NOT NULL DEFAULT '[]',
                    decision_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    activated_at TEXT,
                    invalidated_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES qf_adaptive_sessions(session_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_qf_adaptive_batches_session
                    ON qf_adaptive_microbatches(session_id,ordinal,created_at);

                CREATE TABLE IF NOT EXISTS qf_adaptive_question_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    question_uid TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    plan_revision INTEGER NOT NULL,
                    strategy_profile TEXT NOT NULL,
                    reason TEXT,
                    decision_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_qf_adaptive_decisions_question
                    ON qf_adaptive_question_decisions(question_uid,created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_qf_adaptive_decisions_session
                    ON qf_adaptive_question_decisions(session_id,position);
                """
            )

    def _session(self, session_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM qf_adaptive_sessions WHERE session_id=?", (str(session_id),)).fetchone()
        if not row:
            raise ValueError("Sessão adaptativa não encontrada.")
        return dict(row)

    def _served_uids(self, session_id: str, *, include_prefetched: bool = True) -> set[str]:
        statuses = ("active", "consumed", "prefetched") if include_prefetched else ("active", "consumed")
        placeholders = ",".join("?" for _ in statuses)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT question_ids_json FROM qf_adaptive_microbatches WHERE session_id=? AND status IN ({placeholders})",
                (str(session_id), *statuses),
            ).fetchall()
        result: set[str] = set()
        for row in rows:
            try:
                value = json.loads(str(row["question_ids_json"] or "[]"))
                if isinstance(value, list):
                    result.update(str(item) for item in value if str(item))
            except Exception:
                continue
        return result

    def _triaged_uids(self, session_id: str) -> set[str]:
        """Questões retiradas antes da resposta não consomem a meta da sessão.

        Elas continuam excluídas da seleção da sessão atual para evitar loop, mas o
        orquestrador providencia uma substituta para preservar a quantidade planejada.
        """
        try:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT DISTINCT question_uid FROM qf_learning_events
                    WHERE session_id=?
                      AND event_type IN ('question_correction_requested','topic_not_studied_reported')
                      AND COALESCE(question_uid,'')<>''
                    """,
                    (str(session_id),),
                ).fetchall()
        except sqlite3.Error:
            return set()
        return {str(row["question_uid"] or "") for row in rows if str(row["question_uid"] or "")}

    def _event_attempts(self, session_id: str) -> dict[str, dict[str, Any]]:
        attempts: dict[str, dict[str, Any]] = {}
        try:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT event_type,attempt_id,question_uid,payload_json,occurred_at,seq
                    FROM qf_learning_events
                    WHERE session_id=?
                    ORDER BY occurred_at ASC,seq ASC
                    """,
                    (str(session_id),),
                ).fetchall()
                effects = connection.execute(
                    """
                    SELECT e.attempt_id,e.question_uid,x.detail_json
                    FROM qf_learning_events e
                    JOIN qf_mobile_event_effects x ON x.event_id=e.event_id
                    WHERE e.session_id=? AND e.event_type='answer_submitted'
                    """,
                    (str(session_id),),
                ).fetchall()
        except sqlite3.Error:
            return attempts

        for row in rows:
            attempt_id = str(row["attempt_id"] or "")
            if not attempt_id:
                continue
            item = attempts.setdefault(attempt_id, {"attempt_id": attempt_id, "question_uid": str(row["question_uid"] or "")})
            payload = _safe_json(row["payload_json"])
            event_type = str(row["event_type"] or "")
            if event_type == "confidence_reported":
                item["confidence"] = _norm(payload.get("confidence") or payload.get("level") or payload.get("value"))
            elif event_type == "difficulty_reported":
                item["difficulty"] = _norm(payload.get("perceived_difficulty") or payload.get("difficulty"))
            elif event_type == "learning_gap_reported":
                item["learning_gap"] = bool(payload.get("learning_gap", True))
            elif event_type == "question_skipped":
                item["skipped"] = True
            elif event_type == "answer_submitted":
                item["submitted"] = True
                if "confidence" in payload and not item.get("confidence"):
                    item["confidence"] = _norm(payload.get("confidence"))
                if payload.get("active_response_seconds") is not None:
                    try:
                        item["active_response_seconds"] = float(payload.get("active_response_seconds"))
                    except Exception:
                        pass
        for row in effects:
            attempt_id = str(row["attempt_id"] or "")
            if not attempt_id:
                continue
            item = attempts.setdefault(attempt_id, {"attempt_id": attempt_id, "question_uid": str(row["question_uid"] or "")})
            detail = _safe_json(row["detail_json"])
            if "is_correct" in detail:
                item["is_correct"] = bool(detail.get("is_correct"))
        return attempts

    def evidence(self, session_id: str) -> SessionEvidence:
        attempts = self._event_attempts(session_id)
        evidence = SessionEvidence(focus_topics=[])
        focus_seen: set[tuple[str, str, str]] = set()
        ordered = list(attempts.values())
        for item in ordered:
            uid = str(item.get("question_uid") or "")
            if item.get("skipped") and not item.get("submitted"):
                evidence.skipped += 1
            if "is_correct" not in item:
                continue
            evidence.answered += 1
            correct = bool(item.get("is_correct"))
            confidence = _norm(item.get("confidence"))
            if correct:
                evidence.correct += 1
                if confidence in {"low", "medium", "baixa", "media", "média", "duvida", "dúvida", "incerto"}:
                    evidence.uncertain_correct += 1
            else:
                evidence.wrong += 1
                if confidence in {"high", "alta", "sabia", "sabia bem", "sure"}:
                    evidence.high_confidence_wrong += 1
            if item.get("learning_gap"):
                evidence.learning_gaps += 1
            if uid:
                evidence.last_question_uid = uid
            should_focus = (not correct and confidence in {"high", "alta", "sabia", "sure"}) or (
                correct and confidence in {"low", "medium", "baixa", "media", "média", "duvida", "dúvida", "incerto"}
            ) or bool(item.get("learning_gap"))
            if should_focus and uid:
                try:
                    with self.database.connect() as connection:
                        row = connection.execute(
                            "SELECT subject,primary_topic,lesson FROM questions WHERE uid=?", (uid,)
                        ).fetchone()
                    if row:
                        key = _topic_key(row["subject"], row["primary_topic"], row["lesson"])
                        if key not in focus_seen:
                            focus_seen.add(key)
                            evidence.focus_topics.append({
                                "subject": str(row["subject"] or ""),
                                "topic": str(row["primary_topic"] or ""),
                                "lesson": str(row["lesson"] or ""),
                                "source_question_uid": uid,
                                "reason": "misconception" if (not correct and confidence in {"high", "alta", "sabia", "sure"}) else "uncertain_knowledge",
                            })
                except sqlite3.Error:
                    pass
        return evidence

    @staticmethod
    def _strategy_profile(evidence: SessionEvidence) -> str:
        if evidence.high_confidence_wrong > 0 or evidence.learning_gaps >= 2:
            return "consolidate"
        accuracy = evidence.accuracy
        if evidence.answered >= 3 and accuracy is not None and accuracy < 0.60:
            return "consolidate"
        if evidence.answered >= 3 and accuracy is not None and accuracy >= 0.85 and evidence.uncertain_correct == 0:
            return "expand"
        if evidence.uncertain_correct > 0:
            return "transfer"
        return "balanced"

    def _expected_seconds(self, questions: list[dict[str, Any]]) -> float:
        values: list[float] = []
        for question in questions:
            selection = question.get("selection") if isinstance(question.get("selection"), dict) else {}
            try:
                value = float(selection.get("expected_active_seconds") or 0.0)
            except Exception:
                value = 0.0
            if value > 0:
                values.append(value)
        if values:
            return max(20.0, min(180.0, sum(values) / len(values)))
        return 75.0

    def _goal(self, *, target: int, mode: str, subject: str, profile: str, questions: list[dict[str, Any]]) -> dict[str, Any]:
        focus: list[str] = []
        if mode == "review":
            focus.append("revisões vencidas")
        elif mode == "errors":
            focus.append("pontos com histórico de erro")
        elif mode == "subject" and subject:
            focus.append(subject)
        else:
            focus.extend({
                "consolidate": ["consolidação de pontos frágeis", "revisões importantes"],
                "transfer": ["consolidação e transferência de conceitos", "revisões importantes"],
                "expand": ["avanço em conteúdo novo", "manutenção de revisões"],
                "balanced": ["revisões e prioridades atuais", "avanço equilibrado"],
            }.get(profile, ["prioridades atuais"]))
        for question in questions:
            label = str(question.get("subject") or question.get("materia") or "").strip()
            if label and label not in focus:
                focus.append(label)
            if len(focus) >= 4:
                break
        estimated = max(1, int(round((target * self._expected_seconds(questions)) / 60.0)))
        headline = {
            "consolidate": "Reforçar pontos frágeis sem entrar em repetição mecânica",
            "transfer": "Consolidar o conceito com variação de questões",
            "expand": "Avançar mantendo as revisões essenciais",
            "balanced": "Equilibrar revisão, cobertura e novas questões",
        }.get(profile, "Sessão adaptativa")
        return {
            "type": "adaptive",
            "headline": headline,
            "questions_target": int(target),
            "estimated_minutes": estimated,
            "focus": focus[:4],
            "strategy_profile": profile,
        }

    def _state_signature(self, evidence: SessionEvidence, served_uids: Iterable[str]) -> str:
        payload = {
            "evidence": evidence.to_dict(),
            "served": sorted(str(uid) for uid in served_uids),
        }
        return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()[:20]

    def start_session(
        self,
        *,
        session_id: str,
        learner_id: str,
        device_id: str,
        project_id: str = "",
        mode: str = "recommended",
        subject: str = "",
        target_questions: int = 10,
        micro_batch_size: int = DEFAULT_MICRO_BATCH_SIZE,
        excluded_uids: Iterable[str] = (),
    ) -> dict[str, Any]:
        session_id = str(session_id or "").strip() or str(uuid.uuid4())
        target = max(1, min(50, int(target_questions or 10)))
        micro = max(1, min(MAX_MICRO_BATCH_SIZE, int(micro_batch_size or DEFAULT_MICRO_BATCH_SIZE), target))
        mode = str(mode or "recommended").strip().lower()
        subject = str(subject or "").strip()
        now = _utc_now()
        with self.database.connect() as connection:
            existing = connection.execute("SELECT session_id,status FROM qf_adaptive_sessions WHERE session_id=?", (session_id,)).fetchone()
            if existing:
                return self.session_status(session_id, include_questions=True)
            connection.execute(
                """
                INSERT INTO qf_adaptive_sessions(
                    session_id,learner_id,device_id,exam_project_id,mode,subject,target_questions,
                    micro_batch_size,status,strategy_profile,plan_revision,goal_json,state_signature,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (session_id, str(learner_id or ""), str(device_id or ""), str(project_id or ""), mode, subject,
                 target, micro, "active", "balanced", 0, "{}", "", now, now),
            )
        batch = self._plan_micro_batch(session_id, purpose="active", extra_excluded=set(excluded_uids))
        goal = self._goal(target=target, mode=mode, subject=subject, profile=batch["strategy_profile"], questions=batch["questions"])
        signature = self._state_signature(SessionEvidence(focus_topics=[]), self._served_uids(session_id))
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE qf_adaptive_sessions SET goal_json=?,strategy_profile=?,plan_revision=?,state_signature=?,updated_at=? WHERE session_id=?",
                (_json(goal), batch["strategy_profile"], int(batch["plan_revision"]), signature, _utc_now(), session_id),
            )
        return {
            "contract": "questflow.mobile.adaptive_session.v1",
            "orchestrator": ORCHESTRATOR_VERSION,
            "session_id": session_id,
            "target_questions": target,
            "micro_batch_size": micro,
            "goal": goal,
            "micro_batch": batch,
        }

    def _plan_micro_batch(
        self,
        session_id: str,
        *,
        purpose: str,
        extra_excluded: set[str] | None = None,
        force_replan: bool = False,
    ) -> dict[str, Any]:
        session = self._session(session_id)
        if str(session.get("status") or "") != "active":
            return {"batch_id": "", "questions": [], "completed": True, "reason": "session_not_active"}
        target = int(session.get("target_questions") or 0)
        micro_size = int(session.get("micro_batch_size") or DEFAULT_MICRO_BATCH_SIZE)
        served = self._served_uids(session_id, include_prefetched=not force_replan)
        if force_replan:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE qf_adaptive_microbatches SET status='invalidated',invalidated_at=? WHERE session_id=? AND status='prefetched'",
                    (_utc_now(), session_id),
                )
            served = self._served_uids(session_id, include_prefetched=False)
        triaged = self._triaged_uids(session_id)
        counted_served = served - triaged
        remaining = max(0, target - len(counted_served))
        if remaining <= 0:
            return {"batch_id": "", "questions": [], "completed": True, "reason": "target_reached"}
        count = min(micro_size, remaining)
        evidence = self.evidence(session_id)
        profile = self._strategy_profile(evidence)
        exclusions = set(served)
        exclusions.update(str(uid) for uid in (extra_excluded or set()) if str(uid))
        result = self.study_batch.select_batch(
            count=count,
            mode=str(session.get("mode") or "recommended"),
            subject=str(session.get("subject") or ""),
            project_id=str(session.get("exam_project_id") or ""),
            learner_id=str(session.get("learner_id") or ""),
            excluded_uids=exclusions,
            strategy_profile=profile,
            focus_topics=list(evidence.focus_topics or []),
        )
        questions = list(result.get("questions") or [])
        if not questions:
            return {"batch_id": "", "questions": [], "completed": True, "reason": "no_questions", "strategy_profile": profile}
        goal = self._goal(
            target=target, mode=str(session.get("mode") or "recommended"), subject=str(session.get("subject") or ""),
            profile=profile, questions=questions,
        )
        with self.database.connect() as connection:
            ordinal = int(connection.execute(
                "SELECT COALESCE(MAX(ordinal),0)+1 FROM qf_adaptive_microbatches WHERE session_id=?", (session_id,)
            ).fetchone()[0] or 1)
        revision = int(session.get("plan_revision") or 0) + 1
        batch_id = str(uuid.uuid4())
        state_signature = self._state_signature(evidence, served)
        decision = {
            "orchestrator": ORCHESTRATOR_VERSION,
            "core_policy": str(result.get("core_policy") or ""),
            "batch_policy": str(result.get("policy") or ""),
            "strategy_profile": profile,
            "evidence": evidence.to_dict(),
            "state_signature": state_signature,
            "force_replan": bool(force_replan),
            "target_questions": target,
            "already_served": len(served),
            "counted_toward_target": len(counted_served),
            "triaged_without_attempt": len(triaged),
        }
        now = _utc_now()
        ids = [str(q.get("database_uid") or q.get("uid") or "") for q in questions]
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO qf_adaptive_microbatches(
                    batch_id,session_id,ordinal,plan_revision,purpose,status,strategy_profile,
                    evidence_json,question_ids_json,decision_json,created_at,activated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (batch_id, session_id, ordinal, revision, str(purpose or "active"),
                 "prefetched" if purpose == "prefetch" else "active", profile,
                 _json(evidence.to_dict()), _json(ids), _json(decision), now,
                 None if purpose == "prefetch" else now),
            )
            for position, question in enumerate(questions, start=1):
                selection = question.get("selection") if isinstance(question.get("selection"), dict) else {}
                qid = str(question.get("database_uid") or question.get("uid") or "")
                qdecision = {
                    "selection": selection,
                    "session_strategy": profile,
                    "evidence": evidence.to_dict(),
                    "micro_batch_ordinal": ordinal,
                    "micro_batch_size": len(questions),
                    "state_signature": state_signature,
                }
                connection.execute(
                    """
                    INSERT INTO qf_adaptive_question_decisions(
                        session_id,batch_id,question_uid,position,plan_revision,strategy_profile,reason,decision_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (session_id, batch_id, qid, position, revision, profile,
                     str(selection.get("reason") or "Prioridade adaptativa do QuestFlow"), _json(qdecision), now),
                )
            connection.execute(
                "UPDATE qf_adaptive_sessions SET strategy_profile=?,plan_revision=?,state_signature=?,goal_json=?,updated_at=? WHERE session_id=?",
                (profile, revision, state_signature, _json(goal), now, session_id),
            )
        return {
            "batch_id": batch_id,
            "ordinal": ordinal,
            "plan_revision": revision,
            "purpose": str(purpose or "active"),
            "strategy_profile": profile,
            "state_signature": state_signature,
            "questions": questions,
            "evidence": evidence.to_dict(),
            "goal": goal,
            "completed": False,
        }

    def _prefetch_requires_replan(self, row: Any, session_id: str) -> tuple[bool, str]:
        """Detecta mudança pedagógica relevante ocorrida após o prefetch.

        Não invalida por qualquer evento. O prefetch é descartado apenas quando a
        estratégia de sessão muda ou aparece evidência forte (misconception/gap),
        preservando fluidez sem servir um plano claramente obsoleto.
        """
        stored = _safe_json(row["evidence_json"] if row is not None else "{}")
        current = self.evidence(session_id)
        current_profile = self._strategy_profile(current)
        stored_profile = str(row["strategy_profile"] or "balanced") if row is not None else "balanced"
        if current_profile != stored_profile:
            return True, f"strategy_changed:{stored_profile}->{current_profile}"
        if current.high_confidence_wrong > int(stored.get("high_confidence_wrong") or 0):
            return True, "new_misconception"
        if current.learning_gaps > int(stored.get("learning_gaps") or 0):
            return True, "new_learning_gap"
        return False, ""

    def next_micro_batch(
        self,
        session_id: str,
        *,
        purpose: str = "active",
        prefetched_batch_id: str = "",
        force_replan: bool = False,
        excluded_uids: Iterable[str] = (),
    ) -> dict[str, Any]:
        session_id = str(session_id or "").strip()
        purpose = "prefetch" if str(purpose or "").strip().lower() == "prefetch" else "active"
        if purpose == "prefetch" and not force_replan:
            with self.database.connect() as connection:
                existing = connection.execute(
                    "SELECT * FROM qf_adaptive_microbatches WHERE session_id=? AND status='prefetched' ORDER BY created_at DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
            if existing:
                return {
                    "batch_id": str(existing["batch_id"]),
                    "ordinal": int(existing["ordinal"]),
                    "plan_revision": int(existing["plan_revision"]),
                    "purpose": "prefetch",
                    "strategy_profile": str(existing["strategy_profile"]),
                    "question_ids": [str(uid) for uid in json.loads(str(existing["question_ids_json"] or "[]"))],
                    "questions": [],
                    "evidence": _safe_json(existing["evidence_json"]),
                    "completed": False,
                    "prefetch_reused": True,
                }
        if purpose == "active":
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE qf_adaptive_microbatches SET status='consumed' WHERE session_id=? AND status='active'",
                    (session_id,),
                )
        if purpose == "active" and prefetched_batch_id and not force_replan:
            stale = False
            stale_reason = ""
            with self.database.connect() as connection:
                row = connection.execute(
                    "SELECT * FROM qf_adaptive_microbatches WHERE batch_id=? AND session_id=? AND status='prefetched'",
                    (str(prefetched_batch_id), session_id),
                ).fetchone()
                if row:
                    stale, stale_reason = self._prefetch_requires_replan(row, session_id)
                    if stale:
                        connection.execute(
                            "UPDATE qf_adaptive_microbatches SET status='invalidated',invalidated_at=? WHERE batch_id=?",
                            (_utc_now(), str(prefetched_batch_id)),
                        )
                    else:
                        connection.execute(
                            "UPDATE qf_adaptive_microbatches SET status='active',purpose='active',activated_at=? WHERE batch_id=?",
                            (_utc_now(), str(prefetched_batch_id)),
                        )
                        ids = json.loads(str(row["question_ids_json"] or "[]"))
                        return {
                            "batch_id": str(row["batch_id"]),
                            "ordinal": int(row["ordinal"]),
                            "plan_revision": int(row["plan_revision"]),
                            "purpose": "active",
                            "strategy_profile": str(row["strategy_profile"]),
                            "question_ids": [str(uid) for uid in ids],
                            "questions": [],
                            "evidence": _safe_json(row["evidence_json"]),
                            "completed": False,
                            "prefetch_promoted": True,
                        }
            if stale:
                planned = self._plan_micro_batch(
                    session_id, purpose="active", extra_excluded={str(uid) for uid in excluded_uids if str(uid)}, force_replan=True
                )
                planned["prefetch_invalidated"] = True
                planned["prefetch_invalidation_reason"] = stale_reason
                return planned
        return self._plan_micro_batch(
            session_id,
            purpose=purpose,
            extra_excluded={str(uid) for uid in excluded_uids if str(uid)},
            force_replan=bool(force_replan),
        )

    def mark_batch_consumed(self, session_id: str, batch_id: str) -> None:
        if not batch_id:
            return
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE qf_adaptive_microbatches SET status='consumed' WHERE session_id=? AND batch_id=? AND status='active'",
                (str(session_id), str(batch_id)),
            )

    def finish_session(self, session_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE qf_adaptive_sessions SET status='completed',finished_at=?,updated_at=? WHERE session_id=?",
                (_utc_now(), _utc_now(), str(session_id)),
            )

    def session_status(self, session_id: str, *, include_questions: bool = False) -> dict[str, Any]:
        session = self._session(session_id)
        evidence = self.evidence(session_id)
        with self.database.connect() as connection:
            batches = connection.execute(
                "SELECT * FROM qf_adaptive_microbatches WHERE session_id=? ORDER BY ordinal,created_at",
                (str(session_id),),
            ).fetchall()
        result_batches = []
        for row in batches:
            payload = {
                "batch_id": str(row["batch_id"]),
                "ordinal": int(row["ordinal"]),
                "plan_revision": int(row["plan_revision"]),
                "purpose": str(row["purpose"]),
                "status": str(row["status"]),
                "strategy_profile": str(row["strategy_profile"]),
                "question_ids": json.loads(str(row["question_ids_json"] or "[]")),
                "evidence": _safe_json(row["evidence_json"]),
            }
            if include_questions:
                payload["decision"] = _safe_json(row["decision_json"])
            result_batches.append(payload)
        return {
            "contract": "questflow.mobile.adaptive_session.v1",
            "orchestrator": ORCHESTRATOR_VERSION,
            "session_id": str(session["session_id"]),
            "status": str(session["status"]),
            "target_questions": int(session["target_questions"]),
            "micro_batch_size": int(session["micro_batch_size"]),
            "strategy_profile": str(session["strategy_profile"]),
            "plan_revision": int(session["plan_revision"]),
            "goal": _safe_json(session["goal_json"]),
            "evidence": evidence.to_dict(),
            "batches": result_batches,
        }

    def recent_decisions(self, *, limit: int = 12) -> list[dict[str, Any]]:
        """Últimas decisões adaptativas para explicabilidade exclusiva do Studio."""
        safe_limit = max(1, min(100, int(limit or 12)))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.session_id,d.batch_id,d.question_uid,d.position,d.plan_revision,
                       d.strategy_profile,d.reason,d.decision_json,d.created_at,
                       q.source_code,q.subject,q.primary_topic,q.lesson
                FROM qf_adaptive_question_decisions d
                JOIN questions q ON q.uid=d.question_uid
                ORDER BY d.created_at DESC,d.id DESC LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            decision = _safe_json(row["decision_json"])
            selection = decision.get("selection") if isinstance(decision.get("selection"), dict) else {}
            result.append({
                "session_id": str(row["session_id"] or ""),
                "batch_id": str(row["batch_id"] or ""),
                "question_uid": str(row["question_uid"] or ""),
                "code": str(row["source_code"] or ""),
                "subject": str(row["subject"] or ""),
                "topic": str(row["primary_topic"] or ""),
                "lesson": str(row["lesson"] or ""),
                "position": int(row["position"] or 0),
                "plan_revision": int(row["plan_revision"] or 0),
                "strategy_profile": str(row["strategy_profile"] or ""),
                "reason": str(row["reason"] or ""),
                "expected_active_seconds": selection.get("expected_active_seconds"),
                "topic_transfer": bool(selection.get("topic_transfer")),
                "created_at": str(row["created_at"] or ""),
            })
        return result

    def evaluation_readiness(self) -> dict[str, Any]:
        """Telemetria para comparação futura sem otimizar acerto imediato.

        Não tenta inferir causalidade com poucos dados. Expõe volume de sessões e
        evidência necessária para uma futura comparação de retenção atrasada.
        """
        with self.database.connect() as connection:
            adaptive_sessions = int(connection.execute(
                "SELECT COUNT(*) FROM qf_adaptive_sessions WHERE status='completed'"
            ).fetchone()[0] or 0)
            decisions = int(connection.execute(
                "SELECT COUNT(*) FROM qf_adaptive_question_decisions"
            ).fetchone()[0] or 0)
            delayed = int(connection.execute(
                """
                SELECT COUNT(*) FROM telegram_attempts a
                WHERE EXISTS (
                    SELECT 1 FROM telegram_attempts prior
                    WHERE prior.question_uid=a.question_uid
                      AND prior.answered_at<a.answered_at
                      AND julianday(a.answered_at)-julianday(prior.answered_at)>=1.0
                )
                """
            ).fetchone()[0] or 0)
        minimum_delayed = 30
        return {
            "policy_family": "adaptive_microbatch",
            "adaptive_sessions": adaptive_sessions,
            "adaptive_decisions": decisions,
            "delayed_retention_samples": delayed,
            "minimum_delayed_samples": minimum_delayed,
            "status": "ready" if delayed >= minimum_delayed and adaptive_sessions >= 5 else "insufficient_sample",
            "primary_outcome": "delayed_retention_and_future_mastery",
            "warning": "Acurácia imediata é métrica descritiva; não é o objetivo de otimização do orquestrador.",
        }

    def explain_question(self, question_uid: str, *, session_id: str = "") -> dict[str, Any]:
        uid = str(question_uid or "").strip()
        if not uid:
            raise ValueError("Questão obrigatória.")
        with self.database.connect() as connection:
            if session_id:
                row = connection.execute(
                    """
                    SELECT d.*,q.source_code,q.subject,q.primary_topic,q.lesson
                    FROM qf_adaptive_question_decisions d
                    JOIN questions q ON q.uid=d.question_uid
                    WHERE d.question_uid=? AND d.session_id=?
                    ORDER BY d.created_at DESC,d.id DESC LIMIT 1
                    """,
                    (uid, str(session_id)),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT d.*,q.source_code,q.subject,q.primary_topic,q.lesson
                    FROM qf_adaptive_question_decisions d
                    JOIN questions q ON q.uid=d.question_uid
                    WHERE d.question_uid=?
                    ORDER BY d.created_at DESC,d.id DESC LIMIT 1
                    """,
                    (uid,),
                ).fetchone()
            state = connection.execute(
                """
                SELECT sent_count,correct_count,wrong_count,due_at,memory_retrievability,response_time_ema,
                       kt_mastery,kt_confidence,irt_information,learner_fusion_priority,last_selection_reason,last_selection_bucket
                FROM study_state WHERE question_uid=?
                """,
                (uid,),
            ).fetchone()
        if not row:
            raise ValueError("Ainda não há decisão adaptativa registrada para esta questão.")
        decision = _safe_json(row["decision_json"])
        return {
            "question": {
                "uid": uid,
                "code": str(row["source_code"] or ""),
                "subject": str(row["subject"] or ""),
                "topic": str(row["primary_topic"] or ""),
                "lesson": str(row["lesson"] or ""),
            },
            "session_id": str(row["session_id"]),
            "batch_id": str(row["batch_id"]),
            "position": int(row["position"]),
            "plan_revision": int(row["plan_revision"]),
            "strategy_profile": str(row["strategy_profile"]),
            "reason": str(row["reason"] or ""),
            "decision": decision,
            "learning_state": dict(state) if state else {},
            "created_at": str(row["created_at"]),
            "principle": "A seleção otimiza retenção/domínio futuro; não maximiza apenas acertos imediatos.",
        }


__all__ = [
    "AdaptiveSessionOrchestrator",
    "ORCHESTRATOR_VERSION",
    "DEFAULT_MICRO_BATCH_SIZE",
]
