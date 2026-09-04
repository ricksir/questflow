from __future__ import annotations

"""Learning Engine — execução, recomendação e simulados adaptativos.

O FSRS continua como autoridade de agenda. A Etapa 4 adiciona uma camada
multiobjetivo que só ordena itens dentro da precedência do scheduler e um
simulado que recalcula a próxima questão depois de cada resposta.
"""

import json
import math
import uuid
from typing import Any

from ..learner_model import theta_percentile
from ..recommender import (
    MODEL_VERSION as RECOMMENDER_VERSION,
    blended_projection,
    diversity_adjusted_value,
)
from ..study import SelectionFilters, utc_now


class LearningEngine:
    engine_id = "learning_engine"
    name = "Learning Engine"
    version = "qf-learning-engine-6"

    def __init__(self, database: Any, study: Any, editorial: Any | None = None):
        self.database = database
        self.study = study
        self.editorial = editorial

    @staticmethod
    def _selected_indices(raw: Any) -> list[int]:
        try:
            values = json.loads(str(raw or "[]"))
        except Exception:
            return []
        if not isinstance(values, list):
            return []
        output = []
        for value in values:
            try:
                output.append(int(value))
            except Exception:
                continue
        return output

    def latest_attempt(self, uid: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT a.id, a.question_uid, a.selected_indices_json, a.is_correct,
                       a.answered_at, a.confidence, a.error_type, a.perceived_difficulty,
                       a.learning_gap, a.response_seconds, a.predicted_probability,
                       a.fsrs_predicted_probability, a.source, d.sent_at
                FROM telegram_attempts a
                LEFT JOIN telegram_deliveries d ON d.id=a.delivery_id
                WHERE a.question_uid=?
                ORDER BY a.answered_at DESC, a.id DESC
                LIMIT 1
                """,
                (str(uid),),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["selected_indices"] = self._selected_indices(item.pop("selected_indices_json", "[]"))
        return item

    def recent_errors(self, *, limit: int = 12) -> list[dict]:
        limit = max(1, min(50, int(limit or 12)))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.id AS attempt_id, a.question_uid, a.answered_at, a.confidence,
                       a.error_type, a.perceived_difficulty, a.learning_gap, a.response_seconds,
                       a.source, q.source_code, q.subject, q.primary_topic
                FROM telegram_attempts a
                JOIN questions q ON q.uid=a.question_uid
                WHERE a.is_correct=0
                ORDER BY a.answered_at DESC, a.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ----------------------- Etapa 8 / 6.7: scaffolding ------------------
    def start_scaffold_session(self, uid: str, *, representation: str = "texto", user_prompt: str = "", media_notes: str = "", online: bool = False, learner_snapshot: dict | None = None) -> dict:
        return self.study.start_scaffold_session(
            str(uid), representation=str(representation or "texto"), user_prompt=str(user_prompt or ""), media_notes=str(media_notes or ""),
            online=bool(online), learner_snapshot=learner_snapshot or {},
        )

    def scaffold_session(self, session_id: str) -> dict:
        return self.study.scaffold_session(str(session_id))

    def record_scaffold_event(self, session_id: str, *, level: int, event_type: str, content_preview: str = "", metadata: dict | None = None) -> dict:
        return self.study.record_scaffold_event(
            str(session_id), level=int(level), event_type=str(event_type), content_preview=str(content_preview or ""), metadata=metadata or {},
        )

    def scaffolding_signal(self, uid: str) -> dict:
        return self.study.scaffolding_signal(str(uid))

    def subject_context(self, subject: str, *, limit: int = 30) -> dict:
        clean = str(subject or "").strip()
        if not clean:
            return {"attempts": 0, "accuracy": None, "avg_response_seconds": None}
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS attempts,
                       SUM(CASE WHEN a.is_correct=1 THEN 1 ELSE 0 END) AS correct,
                       AVG(NULLIF(a.response_seconds,0)) AS avg_response_seconds
                FROM telegram_attempts a JOIN questions q ON q.uid=a.question_uid
                WHERE q.subject=?
                ORDER BY a.answered_at DESC
                LIMIT ?
                """,
                (clean, max(1, int(limit))),
            ).fetchone()
        attempts = int(row["attempts"] or 0) if row else 0
        correct = int(row["correct"] or 0) if row else 0
        return {
            "attempts": attempts,
            "accuracy": None if not attempts else round(correct / attempts * 100.0, 1),
            "avg_response_seconds": None if not row or row["avg_response_seconds"] is None else round(float(row["avg_response_seconds"]), 2),
        }

    # ----------------------- Etapa 4: recomendador -----------------------
    @staticmethod
    def _recommendation_question(item: dict) -> dict:
        study = item.get("study_state", {}) if isinstance(item.get("study_state"), dict) else {}
        return {
            "uid": str(item.get("database_uid") or item.get("uid") or ""),
            "code": str(item.get("codigo_origem") or item.get("source_code") or ""),
            "subject": str(item.get("materia") or item.get("subject") or ""),
            "lesson": str(item.get("aula_planilha") or item.get("lesson") or ""),
            "topic": str(item.get("assunto") or item.get("primary_topic") or ""),
            "board": str(item.get("banca") or item.get("board") or ""),
            "statement": str(item.get("enunciado") or item.get("statement") or ""),
            "bucket": int(item.get("selection_bucket", 4) or 4),
            "scheduler_reason": str(item.get("selection_reason") or ""),
            "score": float(item.get("recommendation_score") or 0.0),
            "components": dict(item.get("recommendation_components") or {}),
            "signals": dict(item.get("recommendation_signals") or {}),
            "reasons": list(item.get("recommendation_reasons") or []),
            "mode": str(item.get("recommendation_mode") or "equilibrado"),
            "retrievability": float(item.get("retrievability") or study.get("memory_retrievability") or 0.0),
            "mastery": item.get("knowledge_mastery", study.get("kt_mastery")),
            "mastery_confidence": float(item.get("knowledge_confidence") or study.get("kt_confidence") or 0.0),
            "irt_information": float(item.get("irt_information") or study.get("irt_information") or 0.0),
        }

    def _projection_rows(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT q.subject,
                       COUNT(DISTINCT q.uid) AS question_count,
                       COUNT(a.id) AS attempts,
                       COALESCE(SUM(CASE WHEN a.is_correct=1 THEN 1 ELSE 0 END),0) AS correct
                FROM questions q
                LEFT JOIN telegram_attempts a ON a.question_uid=q.uid
                WHERE COALESCE(TRIM(q.subject),'') <> ''
                GROUP BY q.subject
                ORDER BY q.subject
                """
            ).fetchall()
            mastery_rows = connection.execute(
                """
                SELECT subject, AVG(mastery) AS mastery, AVG(confidence) AS confidence,
                       SUM(exposure_count) AS exposures
                FROM concept_mastery
                WHERE concept_type IN ('assunto','topico','aula')
                GROUP BY subject
                """
            ).fetchall()
            ability_rows = connection.execute(
                "SELECT subject, theta, standard_error, attempt_count FROM learner_ability"
            ).fetchall()
        mastery_map = {str(row["subject"]): dict(row) for row in mastery_rows}
        ability_map = {str(row["subject"]): dict(row) for row in ability_rows}
        output: list[dict] = []
        for row in rows:
            subject = str(row["subject"] or "")
            mastery = mastery_map.get(subject, {})
            ability = ability_map.get(subject, {})
            projection = blended_projection(
                correct=int(row["correct"] or 0),
                attempts=int(row["attempts"] or 0),
                mastery=None if mastery.get("mastery") is None else float(mastery.get("mastery")),
                mastery_confidence=float(mastery.get("confidence") or 0.0),
                theta_scale=None if ability.get("theta") is None else theta_percentile(float(ability.get("theta") or 0.0)),
            )
            output.append({
                "subject": subject,
                "question_count": int(row["question_count"] or 0),
                "attempts": int(row["attempts"] or 0),
                "correct": int(row["correct"] or 0),
                "mastery": None if mastery.get("mastery") is None else round(float(mastery.get("mastery")), 4),
                "mastery_confidence": round(float(mastery.get("confidence") or 0.0), 4),
                "theta_scale": None if ability.get("theta") is None else round(theta_percentile(float(ability.get("theta") or 0.0)), 2),
                "standard_error": None if ability.get("standard_error") is None else round(float(ability.get("standard_error")), 3),
                "projection": projection,
            })
        output.sort(key=lambda item: (item["projection"]["estimate"], -item["question_count"], item["subject"]))
        return output

    def _board_incidence(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(board),''),'Não informada') AS board, COUNT(*) AS total
                FROM questions
                WHERE review_status IN ('aprovado','aprovada','aprovado_automaticamente','autoaprovado','autoaprovada')
                GROUP BY COALESCE(NULLIF(TRIM(board),''),'Não informada')
                ORDER BY total DESC, board
                """
            ).fetchall()
        total = sum(int(row["total"] or 0) for row in rows) or 1
        return [
            {"board": str(row["board"]), "questions": int(row["total"] or 0), "share": round(int(row["total"] or 0) / total, 4)}
            for row in rows[:12]
        ]

    def recommendation_dashboard(self, *, mode: str = "equilibrado", limit: int = 8) -> dict:
        self.study.ensure_learner_model_current()
        filters = SelectionFilters(
            subjects=[], approved_only=True, strategy="adaptativo", recycle_when_empty=True,
            recommendation_mode=str(mode or "equilibrado"),
        )
        # Dashboard/recomendador é pré-visualização: não deve tocar em study_state
        # nem recriar a outbox do Cloud Sync ao atualizar a tela.
        questions = self.study.select_questions(
            filters, max(1, min(20, int(limit or 8))), persist_state=False
        )
        recommendations = [self._recommendation_question(item) for item in questions]
        projections = self._projection_rows()
        weighted = sum(max(1, int(item["question_count"])) for item in projections) or 1
        overall = {
            "estimate": round(sum(item["projection"]["estimate"] * max(1, item["question_count"]) for item in projections) / weighted, 4) if projections else None,
            "low": round(sum(item["projection"]["low"] * max(1, item["question_count"]) for item in projections) / weighted, 4) if projections else None,
            "high": round(sum(item["projection"]["high"] * max(1, item["question_count"]) for item in projections) / weighted, 4) if projections else None,
            "label": "projeção de acerto no conteúdo disponível — não é probabilidade de aprovação",
        }
        with self.database.connect() as connection:
            active = connection.execute(
                """
                SELECT id, mode, target_count, answered_count, correct_count, status, updated_at
                FROM adaptive_simulation_sessions
                WHERE status='em_andamento'
                ORDER BY updated_at DESC LIMIT 1
                """
            ).fetchone()
        return {
            "schema": "questflow.recommender.v1",
            "version": RECOMMENDER_VERSION,
            "mode": str(mode or "equilibrado"),
            "recommendations": recommendations,
            "projections": projections,
            "overall_projection": overall,
            "board_incidence": self._board_incidence(),
            "active_simulation": dict(active) if active else None,
            "principles": ["FSRS precedence", "multiobjective scoring", "diversification", "confidence intervals", "adaptive next-item selection"],
            "caveats": [
                "Incidência da banca é calculada sobre o banco local importado, não sobre todas as provas existentes.",
                "IRT é pessoal e regularizada; não representa calibração populacional.",
                "Projeções expressam acerto esperado no conteúdo disponível e não chance de aprovação.",
            ],
        }

    # ----------------------- simulados adaptativos ------------------------
    @staticmethod
    def _safe_json(raw: Any, default: Any) -> Any:
        try:
            value = json.loads(str(raw or ""))
            return value
        except Exception:
            return default

    @staticmethod
    def _sanitize_mode(value: Any) -> str:
        key = str(value or "equilibrado").strip().lower()
        return key if key in {"equilibrado", "diagnostico", "revisao", "edital"} else "equilibrado"

    def _simulation_row(self, session_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM adaptive_simulation_sessions WHERE id=?", (str(session_id),)
            ).fetchone()
        if not row:
            raise ValueError("Simulado adaptativo não encontrado.")
        item = dict(row)
        item["subjects"] = self._safe_json(item.get("subject_filter_json"), [])
        item["config"] = self._safe_json(item.get("config_json"), {})
        item["projection"] = self._safe_json(item.get("projection_json"), {})
        return item

    def _session_history_counts(self, session_id: str) -> tuple[dict[str, int], dict[tuple[str, str], int], dict[tuple[str, str], int], dict[str, int], str, tuple[str, str] | None]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT q.subject, q.primary_topic, q.lesson, q.board
                FROM adaptive_simulation_items i JOIN questions q ON q.uid=i.question_uid
                WHERE i.session_id=? ORDER BY i.ordinal
                """,
                (str(session_id),),
            ).fetchall()
        subject_counts: dict[str, int] = {}
        topic_counts: dict[tuple[str, str], int] = {}
        lesson_counts: dict[tuple[str, str], int] = {}
        board_counts: dict[str, int] = {}
        last_subject = ""
        last_topic = None
        for row in rows:
            subject = str(row["subject"] or "SEM MATÉRIA")
            topic = str(row["primary_topic"] or "SEM ASSUNTO")
            lesson = str(row["lesson"] or "SEM AULA")
            board = str(row["board"] or "NÃO INFORMADA")
            subject_counts[subject] = subject_counts.get(subject, 0) + 1
            topic_counts[(subject, topic)] = topic_counts.get((subject, topic), 0) + 1
            lesson_counts[(subject, lesson)] = lesson_counts.get((subject, lesson), 0) + 1
            board_counts[board] = board_counts.get(board, 0) + 1
            last_subject, last_topic = subject, (subject, topic)
        return subject_counts, topic_counts, lesson_counts, board_counts, last_subject, last_topic

    def _choose_simulation_candidate(self, session: dict) -> dict | None:
        with self.database.connect() as connection:
            used_rows = connection.execute(
                "SELECT question_uid FROM adaptive_simulation_items WHERE session_id=?", (session["id"],)
            ).fetchall()
        used = tuple(str(row[0]) for row in used_rows)
        candidate_uids = tuple(str(value) for value in (session.get("config") or {}).get("candidate_uids", []) if str(value).strip())
        filters = SelectionFilters(
            subjects=[str(value) for value in session.get("subjects", []) if str(value).strip()],
            approved_only=True,
            strategy="adaptativo",
            recycle_when_empty=True,
            recommendation_mode=self._sanitize_mode(session.get("mode")),
            board=str(session.get("board_filter") or ""),
            exclude_uids=used,
            include_uids=candidate_uids,
        )
        pool = self.study.select_questions(filters, 14)
        if not pool:
            return None
        # Nunca atravessa a precedência FSRS. A diversidade atua apenas entre os
        # candidatos da classe mais urgente presente no pool.
        min_bucket = min(int(item.get("selection_bucket", 4) or 4) for item in pool)
        pool = [item for item in pool if int(item.get("selection_bucket", 4) or 4) == min_bucket]
        subject_counts, topic_counts, lesson_counts, board_counts, last_subject, last_topic = self._session_history_counts(session["id"])
        best = None
        best_value = -1e30
        for item in pool:
            subject = str(item.get("materia") or item.get("subject") or "SEM MATÉRIA")
            topic = str(item.get("assunto") or item.get("primary_topic") or "SEM ASSUNTO")
            lesson = str(item.get("aula_planilha") or item.get("lesson") or "SEM AULA")
            board = str(item.get("banca") or item.get("board") or "NÃO INFORMADA")
            base = float(item.get("recommendation_score") or item.get("learner_fusion_priority") or 0.0)
            value = diversity_adjusted_value(
                base,
                subject_count=subject_counts.get(subject, 0),
                topic_count=topic_counts.get((subject, topic), 0),
                lesson_count=lesson_counts.get((subject, lesson), 0),
                board_count=board_counts.get(board, 0),
                same_as_last_subject=(subject == last_subject),
                same_as_last_topic=((subject, topic) == last_topic),
            )
            if value > best_value:
                best_value, best = value, item
        return best

    def _advance_simulation(self, session_id: str) -> dict:
        session = self._simulation_row(session_id)
        if session["status"] != "em_andamento":
            return session
        candidate = self._choose_simulation_candidate(session)
        now = utc_now()
        if candidate is None:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE adaptive_simulation_sessions SET status='concluido_sem_questoes', current_question_uid=NULL, finished_at=?, updated_at=? WHERE id=?",
                    (now, now, session_id),
                )
            return self._simulation_row(session_id)
        uid = str(candidate.get("database_uid") or candidate.get("uid") or "")
        ordinal = int(session.get("answered_count") or 0) + 1
        snapshot = self.study.question_learning_state(uid)
        recommendation = self._recommendation_question(candidate)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO adaptive_simulation_items(
                    id, session_id, ordinal, question_uid, recommendation_score,
                    recommendation_json, learner_snapshot_json, presented_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), session_id, ordinal, uid,
                    float(recommendation.get("score") or 0.0),
                    json.dumps(recommendation, ensure_ascii=False, sort_keys=True),
                    json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str), now,
                ),
            )
            connection.execute(
                "UPDATE adaptive_simulation_sessions SET current_question_uid=?, updated_at=? WHERE id=?",
                (uid, now, session_id),
            )
        return self._simulation_row(session_id)

    @staticmethod
    def _public_question(question: dict, recommendation: dict | None = None) -> dict:
        alternatives = []
        for index, item in enumerate(question.get("alternativas", []) if isinstance(question.get("alternativas"), list) else []):
            if isinstance(item, dict):
                alternatives.append({"index": index, "key": str(item.get("chave") or chr(65 + index)), "text": str(item.get("texto") or "")})
            else:
                alternatives.append({"index": index, "key": chr(65 + index), "text": str(item)})
        return {
            "uid": str(question.get("database_uid") or question.get("uid") or ""),
            "code": str(question.get("codigo_origem") or question.get("source_code") or ""),
            "subject": str(question.get("materia") or question.get("subject") or ""),
            "lesson": str(question.get("aula_planilha") or question.get("lesson") or ""),
            "topic": str(question.get("assunto") or question.get("primary_topic") or ""),
            "board": str(question.get("banca") or question.get("board") or ""),
            "year": question.get("ano") or question.get("exam_year"),
            "question_type": str(question.get("tipo_questao") or question.get("question_type") or ""),
            "statement": str(question.get("enunciado") or question.get("statement") or ""),
            "alternatives": alternatives,
            "recommendation": recommendation or {},
        }

    def simulation(self, session_id: str) -> dict:
        session = self._simulation_row(session_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT i.*, q.source_code, q.subject, q.primary_topic, q.board
                FROM adaptive_simulation_items i JOIN questions q ON q.uid=i.question_uid
                WHERE i.session_id=? ORDER BY i.ordinal
                """,
                (session_id,),
            ).fetchall()
            current = None
            if session.get("current_question_uid"):
                qrow = connection.execute(
                    "SELECT data_json FROM questions WHERE uid=?", (session["current_question_uid"],)
                ).fetchone()
                irow = connection.execute(
                    "SELECT recommendation_json FROM adaptive_simulation_items WHERE session_id=? AND question_uid=?",
                    (session_id, session["current_question_uid"]),
                ).fetchone()
                if qrow:
                    question = json.loads(qrow["data_json"])
                    question["database_uid"] = session["current_question_uid"]
                    rec = self._safe_json(irow["recommendation_json"], {}) if irow else {}
                    current = self._public_question(question, rec)
        items = []
        for row in rows:
            item = dict(row)
            item["recommendation"] = self._safe_json(item.pop("recommendation_json", "{}"), {})
            item.pop("learner_snapshot_json", None)
            items.append(item)
        target = max(1, int(session.get("target_count") or 1))
        session["progress"] = round(min(1.0, int(session.get("answered_count") or 0) / target), 4)
        session["accuracy"] = None if not int(session.get("answered_count") or 0) else round(int(session.get("correct_count") or 0) / int(session.get("answered_count") or 1), 4)
        return {"session": session, "current": current, "items": items}

    def start_simulation(self, payload: dict | None = None) -> dict:
        payload = dict(payload or {})
        mode = self._sanitize_mode(payload.get("mode"))
        purpose = str(payload.get("purpose") or "simulado_adaptativo").strip() or "simulado_adaptativo"
        min_target = 1 if purpose == "coleta_evidencia" else 5
        target = max(min_target, min(100, int(payload.get("target_count") or (3 if purpose == "coleta_evidencia" else 10))))
        subjects_raw = payload.get("subjects") or []
        subjects = [str(value).strip() for value in subjects_raw if str(value).strip()][:20] if isinstance(subjects_raw, list) else []
        board = str(payload.get("board") or "").strip()
        candidate_uids_raw = payload.get("candidate_uids") or []
        candidate_uids = [str(value).strip() for value in candidate_uids_raw if str(value).strip()][:100] if isinstance(candidate_uids_raw, list) else []
        if candidate_uids:
            target = min(target, len(candidate_uids))
        session_id = str(uuid.uuid4())
        now = utc_now()
        config = {"mode": mode, "target_count": target, "subjects": subjects, "board": board, "adaptive_after_each_answer": True,
                  "purpose": purpose, "concept_key": str(payload.get("concept_key") or ""), "candidate_uids": candidate_uids}
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO adaptive_simulation_sessions(
                    id, mode, target_count, subject_filter_json, board_filter, status,
                    config_json, created_at, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'em_andamento', ?, ?, ?, ?)
                """,
                (session_id, mode, target, json.dumps(subjects, ensure_ascii=False), board or None, json.dumps(config, ensure_ascii=False), now, now, now),
            )
        self._advance_simulation(session_id)
        result = self.simulation(session_id)
        if result["current"] is None:
            raise ValueError("Não há questões elegíveis para iniciar o simulado com os filtros informados.")
        return result

    def start_evidence_collection(self, concept_key: str) -> dict:
        plan = self.study.evidence_collection_plan(str(concept_key), candidate_limit=12)
        if not plan.get("evidence", {}).get("abstain"):
            raise ValueError("Este conceito já possui evidência suficiente; não é necessária coleta diagnóstica agora.")
        if not plan.get("candidate_uids"):
            raise ValueError("Não há questões elegíveis deste conceito para coletar evidência.")
        target = max(1, min(int(plan.get("recommended_questions") or 1), len(plan.get("candidate_uids") or [])))
        result = self.start_simulation({
            "mode": "diagnostico", "target_count": target, "subjects": [str(plan.get("subject") or "")],
            "candidate_uids": list(plan.get("candidate_uids") or []), "purpose": "coleta_evidencia",
            "concept_key": str(plan.get("concept_key") or ""),
        })
        result["evidence_plan"] = plan
        return result

    def submit_simulation_answer(
        self,
        session_id: str,
        selected_index: int,
        *,
        response_seconds: float | None = None,
        confidence: str = "",
        perceived_difficulty: str = "",
        learning_gap: bool | None = None,
    ) -> dict:
        session = self._simulation_row(session_id)
        if session["status"] != "em_andamento" or not session.get("current_question_uid"):
            raise ValueError("O simulado não possui uma questão ativa.")
        uid = str(session["current_question_uid"])
        with self.database.connect() as connection:
            item_row = connection.execute(
                "SELECT id, ordinal FROM adaptive_simulation_items WHERE session_id=? AND question_uid=? AND answered_at IS NULL",
                (session_id, uid),
            ).fetchone()
        if not item_row:
            raise ValueError("A questão atual já foi respondida ou não pertence ao simulado.")
        source = "coleta_evidencia" if str((session.get("config") or {}).get("purpose") or "") == "coleta_evidencia" else "simulado_adaptativo"
        outcome = self.study.record_local_practice_attempt(
            uid, int(selected_index), session_id=session_id, confidence=str(confidence or ""),
            response_seconds=response_seconds, perceived_difficulty=str(perceived_difficulty or ""),
            learning_gap=learning_gap, source=source,
        )
        now = utc_now()
        correct_increment = 1 if outcome["is_correct"] else 0
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE adaptive_simulation_items SET selected_index=?, correct_index=?, is_correct=?,
                    response_seconds=?, confidence=?, answered_at=? WHERE id=?
                """,
                (
                    int(selected_index), int(outcome["correct_index"]), correct_increment,
                    None if response_seconds is None else max(0.0, float(response_seconds)),
                    str(confidence or "") or None, now, item_row["id"],
                ),
            )
            next_answered = int(session.get("answered_count") or 0) + 1
            next_correct = int(session.get("correct_count") or 0) + correct_increment
            evidence_plan = None
            evidence_sufficient = False
            if source == "coleta_evidencia":
                concept_key = str((session.get("config") or {}).get("concept_key") or "")
                if concept_key:
                    try:
                        evidence_plan = self.study.evidence_collection_plan(concept_key, candidate_limit=12)
                        evidence_sufficient = not bool((evidence_plan.get("evidence") or {}).get("abstain"))
                    except ValueError:
                        evidence_plan = None
            finished = next_answered >= int(session.get("target_count") or 1) or evidence_sufficient
            connection.execute(
                """
                UPDATE adaptive_simulation_sessions SET answered_count=?, correct_count=?,
                    current_question_uid=NULL, status=?, finished_at=?, updated_at=? WHERE id=?
                """,
                (next_answered, next_correct, "concluido" if finished else "em_andamento", now if finished else None, now, session_id),
            )
        # A resposta já atualizou FSRS + KT + IRT. Só agora a próxima questão é
        # escolhida, tornando o simulado adaptativo de fato.
        if not finished:
            self._advance_simulation(session_id)
        updated = self.simulation(session_id)
        projection = self.recommendation_dashboard(mode=session.get("mode") or "equilibrado", limit=5).get("overall_projection", {})
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE adaptive_simulation_sessions SET projection_json=?, updated_at=? WHERE id=?",
                (json.dumps(projection, ensure_ascii=False), utc_now(), session_id),
            )
        question = outcome.get("question") or {}
        feedback = {
            "is_correct": bool(outcome["is_correct"]),
            "selected_index": int(selected_index),
            "correct_index": int(outcome["correct_index"]),
            "answer": str(question.get("gabarito") or ""),
            "explanation": str(question.get("explicacao") or ""),
            "fsrs_state": outcome.get("state", {}).get("fsrs_state") if isinstance(outcome.get("state"), dict) else None,
            "learner": self.study.question_learning_state(uid),
        }
        updated["feedback"] = feedback
        updated["projection"] = projection
        if source == "coleta_evidencia":
            updated["evidence_plan"] = evidence_plan or self.study.evidence_collection_plan(str((session.get("config") or {}).get("concept_key") or ""), candidate_limit=12)
            updated["evidence_complete"] = not bool((updated.get("evidence_plan", {}).get("evidence") or {}).get("abstain"))
        return updated

    def abandon_simulation(self, session_id: str) -> dict:
        session = self._simulation_row(session_id)
        if session["status"] == "em_andamento":
            now = utc_now()
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE adaptive_simulation_sessions SET status='abandonado', current_question_uid=NULL, finished_at=?, updated_at=? WHERE id=?",
                    (now, now, session_id),
                )
        return self.simulation(session_id)

    def health(self) -> dict:
        with self.database.connect() as connection:
            attempts = int(connection.execute("SELECT COUNT(*) FROM telegram_attempts").fetchone()[0] or 0)
            states = int(connection.execute("SELECT COUNT(*) FROM study_state").fetchone()[0] or 0)
            simulations = int(connection.execute("SELECT COUNT(*) FROM adaptive_simulation_sessions").fetchone()[0] or 0)
            active = int(connection.execute("SELECT COUNT(*) FROM adaptive_simulation_sessions WHERE status='em_andamento'").fetchone()[0] or 0)
        return {
            "id": self.engine_id,
            "name": self.name,
            "version": self.version,
            "status": "ready",
            "metrics": {
                "attempts": attempts, "study_states": states, "scheduler": "FSRS",
                "recommender": RECOMMENDER_VERSION, "simulations": simulations, "active_simulations": active,
            },
        }


    # ---------------- Central "O que fazer hoje?" 6.5 ----------------
    def today_dashboard(self, project_id: str = "") -> dict:
        """Plano diário explicável orientado pelo projeto de concurso ativo.

        Não cria uma nova agenda: FSRS continua soberano. O projeto/edital
        apenas contextualiza cobertura, lacunas e recomendações.
        """
        project = self.editorial.exam_project_dashboard(project_id) if self.editorial else {"project": None, "items": [], "coverage": {}}
        active = project.get("project") or None
        now_text = utc_now()
        linked_uids: list[str] = []
        if active:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT DISTINCT l.question_uid FROM qf_exam_question_links l
                    JOIN qf_exam_syllabus_items i ON i.id=l.syllabus_item_id
                    JOIN qf_exam_versions v ON v.id=i.version_id
                    WHERE l.project_id=? AND l.active=1
                      AND v.version_no=(SELECT MAX(v2.version_no) FROM qf_exam_versions v2 WHERE v2.project_id=l.project_id)
                    """, (str(active.get("id")),)
                ).fetchall()
                linked_uids=[str(row[0]) for row in rows]
        with self.database.connect() as connection:
            scope_clause = ""
            values: list[Any] = []
            if linked_uids:
                placeholders=",".join("?" for _ in linked_uids)
                scope_clause=f" AND s.question_uid IN ({placeholders})"
                values.extend(linked_uids)
            due = int(connection.execute(
                f"""SELECT COUNT(*) FROM study_state s
                WHERE s.suspended=0 AND s.sent_count>0 AND s.due_at IS NOT NULL AND s.due_at<=?
                  AND COALESCE((SELECT status FROM qf_question_currency qc WHERE qc.question_uid=s.question_uid),'vigente') NOT IN ('desatualizada','anulada','controversa')
                  {scope_clause}""", [now_text,*values]
            ).fetchone()[0] or 0)
            new_count = int(connection.execute(
                f"""SELECT COUNT(*) FROM study_state s
                WHERE s.suspended=0 AND s.sent_count=0
                  AND COALESCE((SELECT status FROM qf_question_currency qc WHERE qc.question_uid=s.question_uid),'vigente') NOT IN ('desatualizada','anulada','controversa')
                  {scope_clause}""", values
            ).fetchone()[0] or 0)
        recs=self.recommendation_dashboard(mode="edital", limit=12).get("recommendations", [])
        linked=set(linked_uids)
        if active and linked:
            scoped=[item for item in recs if str(item.get("uid")) in linked]
            if scoped:
                recs=scoped
        critical=[item for item in (project.get("items") or []) if float(item.get("priority") or 0)>=55][:6]
        coverage=project.get("coverage") or {}
        days=project.get("days_to_exam")
        tasks=[]
        if due:
            tasks.append({"kind":"fsrs","title":f"{due} revisão(ões) vencida(s)", "detail":"Comece pelas revisões FSRS vencidas; o edital não ultrapassa a precedência da memória.","minutes":max(3,round(due*1.4)),"route":"recommend","priority":100})
        if critical:
            tasks.append({"kind":"gaps","title":f"{len(critical)} lacuna(s) prioritária(s) do edital", "detail":"Itens com baixa cobertura, domínio incerto ou maior peso no projeto ativo.","minutes":max(8,len(critical)*4),"route":"examproject","priority":85})
        if recs:
            tasks.append({"kind":"questions","title":f"{min(10,len(recs))} questões de alto valor", "detail":"Selecionadas por FSRS + KT + IRT + sinais do edital e banca.","minutes":max(10,min(10,len(recs))*2),"route":"recommend","priority":75})
        if not due and new_count:
            tasks.append({"kind":"coverage","title":"Avançar cobertura do edital", "detail":f"Há {new_count} questão(ões) novas disponíveis no escopo atual.","minutes":15,"route":"recommend","priority":65})
        if due>=15 or len(critical)>=3:
            tasks.append({"kind":"simulation","title":"Simulado adaptativo recomendado", "detail":"Use uma sessão curta depois das revisões para medir as principais lacunas.","minutes":20,"route":"recommend","priority":55})
        total_minutes=sum(int(item.get("minutes") or 0) for item in tasks[:4])
        return {
            "schema":"questflow.today.v1", "generated_at":now_text, "project":active, "days_to_exam":days,
            "coverage":coverage, "due_reviews":due, "new_questions":new_count, "critical_gaps":critical,
            "recommendations":recs[:8], "tasks":tasks[:5], "estimated_minutes":total_minutes,
            "message": ("Crie ou ative um Projeto de Concurso para orientar o plano pelo edital." if not active else
                       (f"Faltam {days} dia(s) para a prova." if isinstance(days,int) and days>=0 else "Projeto ativo sem contagem regressiva disponível.")),
            "principles":["FSRS precedence","edital coverage","KT uncertainty","IRT information","board incidence","temporal question safety"],
        }
