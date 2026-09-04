# QuestFlow Mobile API v1 — Adaptive Session Orchestrator 6.14.0

A 6.14.0 mantém o contrato geral `questflow.mobile.v1` e acrescenta o contrato de sessão `questflow.mobile.adaptive_session.v1`.

O Mobile não calcula FSRS, KT, IRT, mastery ou prioridade. A seleção e o replanejamento pertencem ao QuestFlow Core/Studio.

## Iniciar sessão adaptativa

`POST /api/v1/mobile/study-sessions`

```json
{
  "session_id": "uuid-do-mobile",
  "count": 20,
  "exam_project_id": "projeto",
  "mode": "recommended",
  "subject": "",
  "micro_batch_size": 3
}
```

Resposta resumida:

```json
{
  "ok": true,
  "data": {
    "contract": "questflow.mobile.adaptive_session.v1",
    "orchestrator": "adaptive-session-orchestrator-v1",
    "session_id": "...",
    "target_questions": 20,
    "micro_batch_size": 3,
    "goal": {
      "type": "adaptive",
      "headline": "Equilibrar revisão, cobertura e novas questões",
      "questions_target": 20,
      "estimated_minutes": 30,
      "focus": [],
      "strategy_profile": "balanced"
    },
    "micro_batch": {
      "batch_id": "...",
      "ordinal": 1,
      "plan_revision": 1,
      "purpose": "active",
      "strategy_profile": "balanced",
      "questions": []
    }
  }
}
```

## Prefetch / próximo micro-lote

`POST /api/v1/mobile/study-sessions/{session_id}/micro-batches`

Prefetch:

```json
{
  "purpose": "prefetch",
  "excluded_question_ids": ["q1", "q2", "q3"]
}
```

Promover prefetch para ativo:

```json
{
  "purpose": "active",
  "prefetched_batch_id": "batch-uuid",
  "excluded_question_ids": ["q1", "q2", "q3"]
}
```

O QuestFlow pode invalidar o prefetch se houver mudança pedagógica relevante. A resposta pode trazer `prefetch_invalidated` e `prefetch_invalidation_reason` no micro-lote recalculado.

## Estado da sessão

`GET /api/v1/mobile/study-sessions/{session_id}`

Retorna objetivo, estratégia, revisão do plano, evidência consolidada e histórico de micro-lotes. O endpoint é somente leitura.

## Eventos

`POST /api/v1/mobile/events:batch` continua sendo o canal de retorno do Mobile para eventos de aprendizagem. A 6.14.0 usa esses eventos para replanejar os próximos micro-lotes.

## Compatibilidade

`POST /api/v1/mobile/question-batches` permanece disponível como caminho compatível/legado e continua usando `StudyBatchService`. A experiência principal do Mobile 0.10.0 utiliza `study-sessions` + `micro-batches`.
