# QuestFlow Mobile API v1 — seleção adaptativa central 6.13.0

O contrato continua `questflow.mobile.v1` e mantém a fronteira Study Only. A mudança da 6.13.0 está em `POST /api/v1/mobile/question-batches`: o lote passa a ser composto pelo `StudyBatchService` sobre a seleção adaptativa central do QuestFlow.

## Requisição

```json
{
  "count": 10,
  "exam_project_id": "...",
  "mode": "recommended",
  "subject": ""
}
```

Modos: `recommended`, `review`, `errors`, `subject`.

## Resposta

Além dos campos públicos da questão, cada item pode trazer `selection` com política, bucket, razão, penalidade de exposição recente, indicador de transferência de conceito e posição no ranking central. `study_flags` inclui `review_eligible`.

O Mobile não calcula FSRS, KT, IRT ou prioridade. Esses sinais permanecem no QuestFlow Core e chegam ao aplicativo já consolidados na decisão do lote.
