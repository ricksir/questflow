from __future__ import annotations

"""Fronteira do modelo do aluno: FSRS + KT + IRT."""

from typing import Any


class LearnerModelEngine:
    engine_id = "learner_model"
    name = "Learner Model"
    version = "qf-learner-engine-4"

    def __init__(self, study: Any):
        self.study = study

    def health(self) -> dict:
        sync = self.study.ensure_learner_model_current()
        dashboard = self.study.learner_model_dashboard()
        return {
            "id": self.engine_id,
            "name": self.name,
            "version": self.version,
            "status": "ready",
            "metrics": {
                "events": int(dashboard.get("events", 0) or 0),
                "concepts": int(dashboard.get("concepts", 0) or 0),
                "modeled_questions": int(dashboard.get("modeled_questions", 0) or 0),
                "abstained_concepts": int(dashboard.get("abstained_concepts", 0) or 0),
                "calibration_samples": int((dashboard.get("calibration") or {}).get("accepted_samples", 0) or 0),
                "sync_action": str(sync.get("action", "none")),
                "scaffold_sessions": int((dashboard.get("scaffolding") or {}).get("sessions", 0) or 0),
                "scaffold_benchmark_observations": int((dashboard.get("scaffolding_benchmark") or {}).get("observations", 0) or 0),
            },
        }

    def question_state(self, uid: str) -> dict:
        self.study.ensure_learner_model_current()
        return self.study.question_learning_state(str(uid))

    def dashboard(self) -> dict:
        sync = self.study.ensure_learner_model_current()
        result = self.study.learner_model_dashboard()
        result["sync"] = sync
        return result

    def rebuild(self) -> dict:
        return self.study.rebuild_learner_model()

    def counterfactual_plan(self, *, target_mastery: float = 0.80, limit: int = 6) -> dict:
        self.study.ensure_learner_model_current()
        return self.study.counterfactual_learning_plan(target_mastery=target_mastery, limit=limit)

    def evidence_collection_plan(self, concept_key: str, *, candidate_limit: int = 10) -> dict:
        self.study.ensure_learner_model_current()
        return self.study.evidence_collection_plan(str(concept_key), candidate_limit=candidate_limit)

    def scaffolding_benchmark(self) -> dict:
        return self.study.scaffolding_benchmark()
