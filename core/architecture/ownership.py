from __future__ import annotations

"""Propriedade explícita das tabelas no SQLite compartilhado.

A propriedade é arquitetural, não um banco separado: somente o módulo dono
pode alterar o schema e escrever diretamente. Outros módulos usam ports/casos
de uso ou eventos internos.
"""

TABLE_OWNERS: dict[str, str] = {
    # Banco editorial e catálogo de questões.
    "imports": "editorial_bank",
    "questions": "editorial_bank",
    "excluded_questions": "editorial_bank",
    "question_code_history": "editorial_bank",
    "question_duplicate_candidates": "editorial_bank",
    "qf_bank_lesson_aliases": "editorial_bank",
    "course_catalog_lessons": "editorial_bank",
    "course_catalog_imports": "editorial_bank",
    "course_catalog_changes": "editorial_bank",
    "qf_exam_projects": "editorial_bank",
    "qf_exam_versions": "editorial_bank",
    "qf_exam_syllabus_items": "editorial_bank",
    "qf_exam_question_links": "editorial_bank",
    "qf_question_currency": "editorial_bank",
    "qf_legislation_versions": "editorial_bank",
    # Conhecimento / retrieval.
    "qf_semantic_signatures": "knowledge",
    "qf_knowledge_nodes": "knowledge",
    "qf_question_concepts": "knowledge",
    "qf_knowledge_edges": "knowledge",
    "qf_rag_chunks": "knowledge",
    # Evidência e modelos do aluno.
    "learner_model_events": "learner_model",
    "concept_mastery": "learner_model",
    "question_irt": "learner_model",
    "learner_ability": "learner_model",
    "learner_profile": "learner_model",
    "fsrs_optimizer_state": "learner_model",
    "adaptive_model_state": "learner_model",
    "topic_learning_state": "learner_model",
    "lesson_learning_state": "learner_model",
    "course_learner_state": "learner_model",
    # Execução do estudo e projeções de aprendizagem.
    "study_state": "learning",
    "study_cycles": "learning",
    "telegram_attempts": "learning",
    "telegram_deliveries": "learning",
    "adaptive_simulation_sessions": "learning",
    "adaptive_simulation_items": "learning",
    "qf_adaptive_sessions": "learning",
    "qf_adaptive_microbatches": "learning",
    "qf_adaptive_question_decisions": "learning",
    "tutor_scaffold_sessions": "learning",
    "tutor_scaffold_events": "learning",
    "studied_scope": "learning",
    "subject_analytics_daily": "learning",
    "xp_events": "learning",
    # IA e governança permanecem separados para avaliação independente.
    "qf_generation_drafts": "ai",
    "qf_error_diagnoses": "ai",
    "qf_ai_interactions": "governance",
    "qf_ai_evaluations": "governance",
    "qf_ai_claims": "governance",
    "qf_ai_claim_evidence": "governance",
    "qf_ai_response_revisions": "governance",
    "qf_ai_provider_metrics": "governance",
    "qf_gold_questions": "governance",
    "qf_gold_expectations": "governance",
    "qf_gold_runs": "governance",
    "qf_gold_run_evaluations": "governance",
    # Mobile é um adapter/projeção, não um segundo Learning Engine.
    "qf_accounts": "mobile",
    "qf_tenants": "mobile",
    "qf_mobile_identity": "mobile",
    "qf_mobile_devices": "mobile",
    "qf_mobile_pairings": "mobile",
    "qf_mobile_sessions": "mobile",
    "qf_mobile_question_revisions": "mobile",
    "qf_mobile_question_snapshots": "mobile",
    "qf_learning_events": "mobile",
    "qf_mobile_event_effects": "mobile",
    "qf_mobile_study_backlog": "mobile",
    # Integrações e runtime transversal.
    "telegram_callback_inbox": "integrations",
    "telegram_outbox": "integrations",
    "telegram_review_requests": "integrations",
    "flow_runtime": "runtime",
    "qf_sync_runtime": "sync",
    "qf_sync_events": "sync",
    "qf_sync_outbox": "sync",
    "qf_sync_outbox_deadletter": "sync",
    "qf_sync_inbox": "sync",
    "qf_sync_conflicts": "sync",
    "qf_sync_devices": "sync",
    "qf_sync_meta": "sync",
    # Kernel arquitetural.
    "qf_internal_events": "platform",
    "qf_event_store": "platform",
    "qf_projection_checkpoints": "platform",
    "schema_migrations": "platform",
}


def module_table_catalog() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for table, owner in TABLE_OWNERS.items():
        result.setdefault(owner, []).append(table)
    return {owner: tuple(sorted(tables)) for owner, tables in sorted(result.items())}


def unknown_tables(connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return sorted(str(row[0]) for row in rows if str(row[0]) not in TABLE_OWNERS)


__all__ = ["TABLE_OWNERS", "module_table_catalog", "unknown_tables"]
