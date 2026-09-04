from __future__ import annotations

"""Registro compatível dos motores de domínio do QuestFlow.

Os seis motores históricos permanecem disponíveis como atributos para não
quebrar integrações. A arquitetura não impõe mais uma contagem: novos motores,
submódulos e serviços podem ser registrados dinamicamente.
"""

from dataclasses import dataclass
from typing import Any

from .editorial_bank import EditorialBankEngine
from .learner_model_engine import LearnerModelEngine
from .learning_engine import LearningEngine
from .knowledge_engine import KnowledgeEngine
from .evaluation_governance import EvaluationGovernanceEngine
from .ai_engine import AIEngine


@dataclass(slots=True)
class EngineRegistry:
    editorial: EditorialBankEngine
    learner: LearnerModelEngine
    learning: LearningEngine
    knowledge: KnowledgeEngine
    ai: AIEngine
    governance: EvaluationGovernanceEngine
    extensions: dict[str, Any] | None = None

    @classmethod
    def build(cls, *, database: Any, queries: Any, commands: Any, study: Any) -> "EngineRegistry":
        editorial = EditorialBankEngine(queries, commands, database)
        learner = LearnerModelEngine(study)
        learning = LearningEngine(database, study, editorial)
        knowledge = KnowledgeEngine(queries, commands)
        governance = EvaluationGovernanceEngine(database)
        ai = AIEngine(editorial, learner, learning, knowledge, governance)
        return cls(
            editorial=editorial,
            learner=learner,
            learning=learning,
            knowledge=knowledge,
            ai=ai,
            governance=governance,
            extensions={},
        )

    def register(self, module_id: str, engine: Any, *, replace: bool = False) -> Any:
        module_id = str(module_id or "").strip()
        if not module_id:
            raise ValueError("O identificador do motor é obrigatório.")
        if self.extensions is None:
            self.extensions = {}
        if module_id in self.extensions and not replace:
            raise ValueError(f"Motor já registrado: {module_id}")
        self.extensions[module_id] = engine
        return engine

    def all(self) -> tuple[Any, ...]:
        historical = (self.editorial, self.learner, self.learning, self.knowledge, self.ai, self.governance)
        return (*historical, *(self.extensions or {}).values())

    def architecture(self) -> dict:
        engines = list(self.all())
        items = []
        for engine in engines:
            try:
                items.append(engine.health())
            except Exception as error:
                items.append({"id": engine.engine_id, "name": engine.name, "version": engine.version, "status": "degraded", "error": str(error), "metrics": {}})
        return {
            "schema": "questflow.architecture.v3",
            "architecture": "extensible_domain_modules",
            "engine_count": len(items),
            "extensible": True,
            "all_ready": all(item.get("status") == "ready" for item in items),
            "engines": items,
            "principles": [
                "offline_first", "human_in_the_loop", "auditable_ai", "fsrs_precedence",
                "rag_grounding", "incremental_migrations", "separation_of_generation_and_evaluation",
                "multiobjective_recommendation", "adaptive_simulation", "confidence_intervals",
                "selected_source_generation", "temporal_legislation", "gold_regression",
                "exam_project_centric", "edital_versioning", "temporal_question_status",
                "structured_outputs", "prompt_injection_defense", "privacy_minimization", "ai_observability",
                "selective_prediction", "calibration_monitoring", "counterfactual_learning_plans",
                "runtime_watchdog", "self_healing_services", "bounded_async_io", "rate_limiting", "version_compatibility",
                "progressive_scaffolding", "multimodal_local_review", "scaffold_support_signal",
                "actionable_evidence_collection", "scaffolding_retention_benchmark",
                "multimodal_rag_3", "interchangeable_retrieval_backends", "auditable_multimodal_grounding", "binary_media_explicit_opt_in",
                "multimodal_grounding_benchmark", "gold_retrieval_regression", "hybrid_gain_measurement",
                "calibrated_reranking", "versioned_retrieval_thresholds", "continuous_retrieval_regression", "human_approved_retrieval_profile",
                "retrieval_observability", "index_drift_detection", "assisted_gold_expansion", "exportable_retrieval_reports",
                "retrieval_quality_gates", "release_quarantine", "human_audited_release_override", "safe_retrieval_release_rollback",
                "modular_monolith", "hexagonal_boundaries", "vertical_modules", "explicit_table_ownership",
                "internal_domain_events", "selective_event_sourcing", "rebuildable_projections", "versioned_studio_api",
            ],
        }
