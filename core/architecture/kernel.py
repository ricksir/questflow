from __future__ import annotations

from typing import Any

from .events import InternalEventBus, SelectiveEventStore
from .modules import ModuleManifest, ModuleRegistry
from .ownership import module_table_catalog, unknown_tables
from .projections import ProjectionCatalog, ProjectionDefinition


MODULE_NAMES = {
    "editorial_bank": "Banco Editorial",
    "learner_model": "Learner Model",
    "learning": "Learning Engine",
    "knowledge": "Knowledge Engine",
    "ai": "AI Engine",
    "governance": "Evaluation & Governance",
    "mobile": "Mobile Adapter",
    "integrations": "Integrações",
    "runtime": "Runtime",
    "sync": "Sincronização",
    "platform": "Plataforma",
}


class ArchitectureKernel:
    """Composition root interno do monólito modular."""

    def __init__(self, database: Any, *, engines: Any | None = None, study: Any | None = None) -> None:
        self.database = database
        self.events = InternalEventBus(database)
        self.event_store = SelectiveEventStore(database)
        self.projections = ProjectionCatalog(database)
        self.modules = ModuleRegistry()
        self._register_modules(engines)
        self._register_projections(study)
        self._register_internal_handlers(study)

    def _register_modules(self, engines: Any | None) -> None:
        table_catalog = module_table_catalog()
        engine_instances = {
            "editorial_bank": getattr(engines, "editorial", None),
            "learner_model": getattr(engines, "learner", None),
            "learning": getattr(engines, "learning", None),
            "knowledge": getattr(engines, "knowledge", None),
            "ai": getattr(engines, "ai", None),
            "governance": getattr(engines, "governance", None),
        }
        dependencies = {
            "learning": ("editorial_bank", "learner_model"),
            "ai": ("editorial_bank", "learner_model", "learning", "knowledge", "governance"),
            "mobile": ("learning",),
            "sync": ("platform",),
            "integrations": ("learning",),
        }
        for module_id, tables in table_catalog.items():
            instance = engine_instances.get(module_id)
            kind = "domain" if module_id in engine_instances else "transversal"
            version = str(getattr(instance, "version", "1"))
            self.modules.register(ModuleManifest(
                module_id=module_id,
                name=MODULE_NAMES.get(module_id, module_id.replace("_", " ").title()),
                kind=kind,
                version=version,
                owns_tables=tables,
                dependencies=dependencies.get(module_id, ()),
                instance=instance,
            ))
        self.modules.validate()

    def _register_projections(self, study: Any | None) -> None:
        if study is None:
            return

        def rebuild_learner() -> Any:
            return study.rebuild_learner_model()

        def rebuild_analytics() -> Any:
            return study.rebuild_subject_analytics_daily()

        self.projections.register(ProjectionDefinition(
            name="learner.fsrs_kt_irt",
            owner="learner_model",
            source_streams=("attempt", "learning"),
            rebuild=rebuild_learner,
            target_tables=("study_state", "concept_mastery", "question_irt", "learner_ability"),
        ))
        self.projections.register(ProjectionDefinition(
            name="learning.analytics",
            owner="learning",
            source_streams=("attempt", "learning"),
            rebuild=rebuild_analytics,
            target_tables=("subject_analytics_daily",),
        ))

    def _register_internal_handlers(self, study: Any | None) -> None:
        if study is None:
            return

        # Efeito editorial -> learning sem escrita direta na tabela/projeção
        # pertencente a outro módulo. O evento fica durável antes do handler.
        self.events.subscribe(
            "editorial.question.changed",
            lambda _event: self.projections.rebuild("learning.analytics"),
        )

    def architecture(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            unknown = unknown_tables(connection)
        return {
            "schema": "questflow.architecture.v3",
            "architecture": "modular_monolith_hexagonal",
            "database": {
                "engine": "sqlite",
                "shared": True,
                "table_ownership_explicit": True,
                "unknown_tables": unknown,
            },
            "eventing": {
                "internal_outbox": "qf_internal_events -> qf_sync_outbox",
                "selective_event_store": "qf_event_store",
                "event_sourced_streams": sorted(self.event_store.ALLOWED_STREAMS),
            },
            "modules": self.modules.public(),
            "projections": {
                "rebuildable": True,
                "items": self.projections.status(),
            },
        }


__all__ = ["ArchitectureKernel"]
