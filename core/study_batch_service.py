from __future__ import annotations

"""Composição de sessões de estudo sobre a inteligência central do QuestFlow.

O serviço NÃO cria um segundo recomendador. Ele consome ``StudyRepository.select_questions``
como fonte autoritativa (FSRS + KT + IRT + learner fusion + cobertura + banca) e aplica apenas
políticas de sessão: mix recomendado, interleaving, proteção contra exposição recente e
transferência de conceito após baixa confiança.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import sqlite3
from typing import Any, Iterable

from .study import SelectionFilters, StudyRepository


POLICY_VERSION = "recommended-adaptive-v2"
CORE_POLICY = "auditor_inteligente"
RECENT_SESSION_COUNT = 3
MAX_CANDIDATE_POOL = 320


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _topic_key(subject: Any, topic: Any, lesson: Any) -> tuple[str, str, str]:
    return (_norm(subject), _norm(topic), _norm(lesson))


def _safe_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@dataclass(slots=True)
class ExposureContext:
    recent_counts: dict[str, int]
    last_session_uids: set[str]
    previous_opening_uid: str
    uncertain_topics: list[tuple[tuple[str, str, str], str]]
    focus_topics: list[tuple[tuple[str, str, str], str, str]]


class StudyBatchService:
    """Fonte única de lotes para clientes de estudo.

    O Studio/Core decide *quais itens são pedagogicamente prioritários*; este serviço decide
    *como compor a sessão* sem descaracterizar a precedência do motor central.
    """

    def __init__(self, database: Any, study: StudyRepository):
        self.database = database
        self.study = study

    def _project_uids(self, project_id: str) -> set[str] | None:
        project_id = str(project_id or "").strip()
        if not project_id:
            return None
        try:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT question_uid FROM qf_exam_question_links
                    WHERE project_id=? AND COALESCE(active,1)=1
                    """,
                    (project_id,),
                ).fetchall()
            return {str(row["question_uid"]) for row in rows}
        except sqlite3.Error:
            # Sem o módulo de projetos não há um escopo válido a aplicar.
            return set()

    def _error_uids(self) -> set[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT question_uid FROM study_state WHERE COALESCE(wrong_count,0)>0 AND COALESCE(suspended,0)=0"
            ).fetchall()
        return {str(row["question_uid"]) for row in rows}

    def _review_uids(self) -> set[str]:
        now = _utc_now().isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT question_uid FROM study_state
                WHERE COALESCE(suspended,0)=0
                  AND (COALESCE(correction_priority,0)=1 OR (due_at IS NOT NULL AND due_at<=?))
                """,
                (now,),
            ).fetchall()
        return {str(row["question_uid"]) for row in rows}

    def _recent_exposure_context(self, *, learner_id: str = "", project_id: str = "") -> ExposureContext:
        recent_counts: dict[str, int] = {}
        last_session_uids: set[str] = set()
        previous_opening_uid = ""
        uncertain_topics: list[tuple[tuple[str, str, str], str]] = []
        try:
            with self.database.connect() as connection:
                params: list[Any] = []
                clauses = ["event_type='session_started'", "COALESCE(session_id,'')<>''"]
                if learner_id:
                    clauses.append("learner_id=?")
                    params.append(str(learner_id))
                if project_id:
                    clauses.append("COALESCE(exam_project_id,'')=?")
                    params.append(str(project_id))
                session_rows = connection.execute(
                    f"""
                    SELECT session_id,MAX(occurred_at) AS occurred_at
                    FROM qf_learning_events
                    WHERE {' AND '.join(clauses)}
                    GROUP BY session_id
                    ORDER BY occurred_at DESC
                    LIMIT ?
                    """,
                    (*params, RECENT_SESSION_COUNT),
                ).fetchall()
                session_ids = [str(row["session_id"]) for row in session_rows if row["session_id"]]
                for session_index, session_id in enumerate(session_ids):
                    rows = connection.execute(
                        """
                        SELECT question_uid,payload_json,occurred_at
                        FROM qf_learning_events
                        WHERE session_id=? AND event_type='question_presented' AND COALESCE(question_uid,'')<>''
                        ORDER BY occurred_at ASC,seq ASC
                        """,
                        (session_id,),
                    ).fetchall()
                    for index, row in enumerate(rows):
                        uid = str(row["question_uid"] or "")
                        if not uid:
                            continue
                        # A sessão mais recente pesa mais; questão pulada também conta porque foi exposta.
                        weight = max(1, RECENT_SESSION_COUNT - session_index)
                        recent_counts[uid] = recent_counts.get(uid, 0) + weight
                        if session_index == 0:
                            last_session_uids.add(uid)
                            payload = _safe_json(row["payload_json"])
                            position = int(payload.get("position") or (index + 1))
                            if position == 1 and not previous_opening_uid:
                                previous_opening_uid = uid
                    if session_index == 0 and rows and not previous_opening_uid:
                        previous_opening_uid = str(rows[0]["question_uid"] or "")

                confidence_params: list[Any] = []
                confidence_clauses = ["e.event_type='confidence_reported'", "COALESCE(e.question_uid,'')<>''"]
                if learner_id:
                    confidence_clauses.append("e.learner_id=?")
                    confidence_params.append(str(learner_id))
                if project_id:
                    confidence_clauses.append("COALESCE(e.exam_project_id,'')=?")
                    confidence_params.append(str(project_id))
                confidence_rows = connection.execute(
                    f"""
                    SELECT e.question_uid,e.payload_json,q.subject,q.primary_topic,q.lesson
                    FROM qf_learning_events e
                    JOIN questions q ON q.uid=e.question_uid
                    WHERE {' AND '.join(confidence_clauses)}
                    ORDER BY e.occurred_at DESC,e.seq DESC
                    LIMIT 24
                    """,
                    tuple(confidence_params),
                ).fetchall()
                seen_topic_keys: set[tuple[str, str, str]] = set()
                for row in confidence_rows:
                    payload = _safe_json(row["payload_json"])
                    confidence = _norm(payload.get("confidence") or payload.get("level") or payload.get("value"))
                    if confidence not in {"low", "medium", "baixa", "media", "média", "duvida", "dúvida", "incerto"}:
                        continue
                    key = _topic_key(row["subject"], row["primary_topic"], row["lesson"])
                    if key in seen_topic_keys:
                        continue
                    seen_topic_keys.add(key)
                    uncertain_topics.append((key, str(row["question_uid"] or "")))
                    if len(uncertain_topics) >= 6:
                        break
        except sqlite3.Error:
            pass
        return ExposureContext(
            recent_counts=recent_counts,
            last_session_uids=last_session_uids,
            previous_opening_uid=previous_opening_uid,
            uncertain_topics=uncertain_topics,
            focus_topics=[],
        )

    @staticmethod
    def _selection_bucket(question: dict[str, Any]) -> int:
        try:
            return int(question.get("selection_bucket", 9))
        except Exception:
            return 9

    @staticmethod
    def _uid(question: dict[str, Any]) -> str:
        return str(question.get("database_uid") or question.get("uid") or "")

    @staticmethod
    def _state(question: dict[str, Any]) -> dict[str, Any]:
        value = question.get("study_state")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _question_topic_key(question: dict[str, Any]) -> tuple[str, str, str]:
        return _topic_key(
            question.get("materia") or question.get("subject"),
            question.get("assunto") or question.get("primary_topic"),
            question.get("aula_planilha") or question.get("lesson"),
        )

    def _core_candidates(
        self,
        *,
        count: int,
        mode: str,
        subject: str,
        project_id: str,
        excluded_uids: set[str],
    ) -> list[dict[str, Any]]:
        project_uids = self._project_uids(project_id)
        if project_uids is not None and not project_uids:
            return []

        include_uids: set[str] | None = None if project_uids is None else set(project_uids)
        if mode == "errors":
            error_uids = self._error_uids()
            include_uids = error_uids if include_uids is None else include_uids.intersection(error_uids)
            if not include_uids:
                return []
        elif mode == "review":
            review_uids = self._review_uids()
            include_uids = review_uids if include_uids is None else include_uids.intersection(review_uids)
            if not include_uids:
                return []

        subjects = [str(subject).strip()] if mode == "subject" and str(subject).strip() else []
        candidate_limit = min(MAX_CANDIDATE_POOL, max(80, int(count) * 10))
        filters = SelectionFilters(
            subjects=subjects,
            approved_only=True,
            strategy="erros_primeiro" if mode == "errors" else CORE_POLICY,
            recycle_when_empty=True,
            recommendation_mode="equilibrado",
            exclude_uids=tuple(sorted(str(uid) for uid in excluded_uids if str(uid))),
            include_uids=tuple(sorted(include_uids)) if include_uids is not None else (),
        )
        return self.study.select_questions(filters, candidate_limit, persist_state=False)

    @staticmethod
    def _recent_penalty(question: dict[str, Any], exposure: ExposureContext) -> float:
        uid = StudyBatchService._uid(question)
        bucket = StudyBatchService._selection_bucket(question)
        if bucket in {0, 1}:  # correção/relearning crítico nunca é suprimido por UX de rotação
            return 0.0
        count = float(exposure.recent_counts.get(uid, 0))
        penalty = count * 22.0
        if uid in exposure.last_session_uids:
            penalty += 38.0
        if uid and uid == exposure.previous_opening_uid:
            penalty += 120.0
        if bucket == 2:  # revisão realmente vencida recebe apenas metade da penalidade
            penalty *= 0.50
        return penalty

    def _transfer_match(self, question: dict[str, Any], exposure: ExposureContext) -> tuple[bool, str]:
        key = self._question_topic_key(question)
        uid = self._uid(question)
        # Focos do AdaptiveSessionOrchestrator têm precedência: erro com confiança
        # alta (misconception), acerto incerto ou gap declarado pedem uma questão
        # diferente do mesmo conceito antes de repetir exatamente o mesmo item.
        for target_key, source_uid, _reason in exposure.focus_topics:
            same_concept = key[:2] == target_key[:2] and all(key[:2])
            if same_concept and uid != source_uid:
                return True, source_uid
        for target_key, source_uid in exposure.uncertain_topics:
            # Conceito = matéria + assunto. Aula é usada como desempate, não como barreira absoluta.
            same_concept = key[:2] == target_key[:2] and all(key[:2])
            if same_concept and uid != source_uid:
                return True, source_uid
        return False, ""

    def _annotate(self, candidates: list[dict[str, Any]], exposure: ExposureContext) -> None:
        for rank, question in enumerate(candidates):
            transfer, source_uid = self._transfer_match(question, exposure)
            penalty = self._recent_penalty(question, exposure)
            state = self._state(question)
            try:
                response_ema = float(state.get("response_time_ema") or 0.0)
            except Exception:
                response_ema = 0.0
            # Tempo esperado é contexto de qualidade, nunca limite. IRT e histórico
            # modulam a estimativa apenas quando há evidência suficiente.
            try:
                irt_information = max(0.0, float(state.get("irt_information") or 0.0))
            except Exception:
                irt_information = 0.0
            expected_seconds = response_ema if response_ema > 0 else 75.0
            if response_ema <= 0 and irt_information > 0.75:
                expected_seconds = 82.0
            expected_seconds = max(20.0, min(180.0, expected_seconds))
            focus_reason = ""
            if transfer:
                for target_key, target_uid, reason in exposure.focus_topics:
                    if target_uid == source_uid and self._question_topic_key(question)[:2] == target_key[:2]:
                        focus_reason = reason
                        break
            question["_session_policy"] = {
                "core_rank": rank,
                "recent_exposure_penalty": penalty,
                "topic_transfer": transfer,
                "transfer_source_uid": source_uid,
                "focus_reason": focus_reason,
                "expected_active_seconds": round(expected_seconds, 1),
            }

    def _pick_diverse(
        self,
        pool: Iterable[dict[str, Any]],
        *,
        needed: int,
        selected: list[dict[str, Any]],
        selected_uids: set[str],
    ) -> None:
        candidates = [q for q in pool if self._uid(q) not in selected_uids]
        subject_counts: dict[str, int] = {}
        topic_counts: dict[tuple[str, str], int] = {}
        lesson_counts: dict[tuple[str, str, str], int] = {}
        for q in selected:
            key = self._question_topic_key(q)
            subject_counts[key[0]] = subject_counts.get(key[0], 0) + 1
            topic_counts[key[:2]] = topic_counts.get(key[:2], 0) + 1
            lesson_counts[key] = lesson_counts.get(key, 0) + 1
        while candidates and needed > 0:
            best: dict[str, Any] | None = None
            best_value = -1e30
            last_key = self._question_topic_key(selected[-1]) if selected else ("", "", "")
            previous_key = self._question_topic_key(selected[-2]) if len(selected) > 1 else ("", "", "")
            for question in candidates:
                meta = question.get("_session_policy") if isinstance(question.get("_session_policy"), dict) else {}
                rank = int(meta.get("core_rank") or 0)
                penalty = float(meta.get("recent_exposure_penalty") or 0.0)
                transfer_bonus = 70.0 if bool(meta.get("topic_transfer")) else 0.0
                key = self._question_topic_key(question)
                diversity_penalty = (
                    subject_counts.get(key[0], 0) * 8.0
                    + topic_counts.get(key[:2], 0) * 12.0
                    + lesson_counts.get(key, 0) * 5.0
                )
                if key[:2] == last_key[:2] and all(key[:2]):
                    diversity_penalty += 18.0
                    # Anti-loop pedagógico: três questões consecutivas do mesmo
                    # conceito só vencem esta penalidade se a prioridade central
                    # for realmente muito superior às alternativas.
                    if key[:2] == previous_key[:2] and all(previous_key[:2]):
                        diversity_penalty += 150.0
                elif key[0] == last_key[0] and key[0]:
                    diversity_penalty += 7.0
                value = 10000.0 - rank * 11.0 - penalty - diversity_penalty + transfer_bonus
                if value > best_value:
                    best_value = value
                    best = question
            if best is None:
                break
            candidates.remove(best)
            selected.append(best)
            selected_uids.add(self._uid(best))
            key = self._question_topic_key(best)
            subject_counts[key[0]] = subject_counts.get(key[0], 0) + 1
            topic_counts[key[:2]] = topic_counts.get(key[:2], 0) + 1
            lesson_counts[key] = lesson_counts.get(key, 0) + 1
            needed -= 1

    def _compose_recommended(
        self, candidates: list[dict[str, Any]], count: int, exposure: ExposureContext, *, strategy_profile: str = "balanced"
    ) -> list[dict[str, Any]]:
        self._annotate(candidates, exposure)
        selected: list[dict[str, Any]] = []
        selected_uids: set[str] = set()

        critical = [q for q in candidates if self._selection_bucket(q) in {0, 1}]
        self._pick_diverse(critical, needed=min(count, len(critical)), selected=selected, selected_uids=selected_uids)
        if len(selected) >= count:
            return selected[:count]

        # Um acerto com baixa/média confiança pede transferência do conceito antes de
        # reapresentar o mesmo item. O candidato usa a inteligência central e só ganha
        # prioridade de composição da sessão.
        transfer = [q for q in candidates if bool((q.get("_session_policy") or {}).get("topic_transfer"))]
        profile = str(strategy_profile or "balanced").strip().lower()
        transfer_ratio = {"consolidate": 0.25, "transfer": 0.34, "expand": 0.12, "balanced": 0.18}.get(profile, 0.18)
        transfer_target = max(1, int(math.ceil(count * transfer_ratio))) if transfer else 0
        self._pick_diverse(transfer, needed=min(transfer_target, count - len(selected)), selected=selected, selected_uids=selected_uids)

        due = [q for q in candidates if self._selection_bucket(q) == 2]
        new = [q for q in candidates if self._selection_bucket(q) == 3]
        due_ratio = {"consolidate": 0.58, "transfer": 0.46, "expand": 0.28, "balanced": 0.40}.get(profile, 0.40)
        new_ratio = {"consolidate": 0.12, "transfer": 0.22, "expand": 0.48, "balanced": 0.35}.get(profile, 0.35)
        due_target = max(1, int(math.ceil(count * due_ratio))) if due else 0
        new_target = max(1, int(math.floor(count * new_ratio))) if new else 0
        current_due = sum(1 for q in selected if self._selection_bucket(q) == 2)
        current_new = sum(1 for q in selected if self._selection_bucket(q) == 3)
        self._pick_diverse(due, needed=min(max(0, due_target - current_due), count - len(selected)), selected=selected, selected_uids=selected_uids)
        self._pick_diverse(new, needed=min(max(0, new_target - current_new), count - len(selected)), selected=selected, selected_uids=selected_uids)

        # Preenche com a ordem adaptativa central, aplicando interleaving e cooldown.
        self._pick_diverse(candidates, needed=count - len(selected), selected=selected, selected_uids=selected_uids)

        # Proteção explícita da primeira posição entre sessões. Só uma correção/relearning
        # crítico pode justificar repetir o mesmo item de abertura.
        if selected and self._uid(selected[0]) == exposure.previous_opening_uid and self._selection_bucket(selected[0]) not in {0, 1}:
            for index in range(1, len(selected)):
                if self._uid(selected[index]) != exposure.previous_opening_uid:
                    selected[0], selected[index] = selected[index], selected[0]
                    break
        return selected[:count]

    def _compose_mode(self, candidates: list[dict[str, Any]], count: int, exposure: ExposureContext) -> list[dict[str, Any]]:
        self._annotate(candidates, exposure)
        selected: list[dict[str, Any]] = []
        self._pick_diverse(candidates, needed=count, selected=selected, selected_uids=set())
        if selected and self._uid(selected[0]) == exposure.previous_opening_uid and self._selection_bucket(selected[0]) not in {0, 1}:
            for index in range(1, len(selected)):
                if self._uid(selected[index]) != exposure.previous_opening_uid:
                    selected[0], selected[index] = selected[index], selected[0]
                    break
        return selected[:count]

    def select_batch(
        self,
        *,
        count: int,
        mode: str = "recommended",
        subject: str = "",
        project_id: str = "",
        learner_id: str = "",
        excluded_uids: Iterable[str] = (),
        strategy_profile: str = "balanced",
        focus_topics: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        count = max(1, min(50, int(count or 8)))
        mode = str(mode or "recommended").strip().lower()
        if mode not in {"recommended", "review", "errors", "subject"}:
            mode = "recommended"
        if mode == "subject" and not str(subject or "").strip():
            raise ValueError("Uma matéria deve ser informada para a sessão por matéria.")

        exclusions = {str(uid) for uid in excluded_uids if str(uid)}
        candidates = self._core_candidates(
            count=count,
            mode=mode,
            subject=subject,
            project_id=project_id,
            excluded_uids=exclusions,
        )
        exposure = self._recent_exposure_context(learner_id=learner_id, project_id=project_id)
        focus: list[tuple[tuple[str, str, str], str, str]] = []
        for item in focus_topics or ():
            if not isinstance(item, dict):
                continue
            key = _topic_key(item.get("subject"), item.get("topic"), item.get("lesson"))
            if not any(key[:2]):
                continue
            focus.append((key, str(item.get("source_question_uid") or ""), str(item.get("reason") or "session_focus")))
        exposure.focus_topics = focus
        selected = (
            self._compose_recommended(candidates, count, exposure, strategy_profile=strategy_profile)
            if mode == "recommended"
            else self._compose_mode(candidates, count, exposure)
        )

        for question in selected:
            meta = question.get("_session_policy") if isinstance(question.get("_session_policy"), dict) else {}
            question["selection"] = {
                "policy": POLICY_VERSION if mode == "recommended" else f"{mode}-adaptive-v2",
                "source": "StudyRepository.select_questions",
                "core_policy": CORE_POLICY,
                "bucket": self._selection_bucket(question),
                "reason": str(question.get("selection_reason") or "Prioridade adaptativa do QuestFlow"),
                "recent_exposure_penalty": round(float(meta.get("recent_exposure_penalty") or 0.0), 2),
                "topic_transfer": bool(meta.get("topic_transfer")),
                "transfer_reason": str(meta.get("focus_reason") or ""),
                "core_rank": int(meta.get("core_rank") or 0),
                "strategy_profile": str(strategy_profile or "balanced"),
                "expected_active_seconds": float(meta.get("expected_active_seconds") or 75.0),
                "review_eligible": mode == "review" or self._selection_bucket(question) in {0, 1, 2},
            }
            question.pop("_session_policy", None)

        return {
            "policy": POLICY_VERSION if mode == "recommended" else f"{mode}-adaptive-v2",
            "core_policy": CORE_POLICY,
            "generated_at": _utc_now().isoformat(),
            "mode": mode,
            "questions": selected,
            "diagnostics": {
                "candidate_count": len(candidates),
                "recent_session_count": RECENT_SESSION_COUNT,
                "previous_opening_uid": exposure.previous_opening_uid,
                "uncertain_topic_count": len(exposure.uncertain_topics),
                "session_focus_count": len(exposure.focus_topics),
                "strategy_profile": str(strategy_profile or "balanced"),
            },
        }


__all__ = ["StudyBatchService", "POLICY_VERSION", "CORE_POLICY"]
