# QuestFlow Mobile Analytics V2

`GET /api/v1/mobile/analytics?exam_project_id=&range=12w&grain=week`

O contrato `questflow.analytics.v2` retorna `summary`, `timeline`, `subjects`,
`priority_breakdown`, `projection_band`, `review_queue`, `sample_size`,
`generated_at` e `source_freshness`.

- `range`: `4w`, `8w`, `12w` ou `24w`.
- `grain`: `day` ou `week`.
- `exam_project_id`: opcional; restringe a análise ao projeto selecionado.
- `timeline`: contém apenas agregações de tentativas persistidas.
- `projection_band`: intervalo Wilson de 95%, com denominador explícito.
- Retenção histórica não é simulada: permanece nula até existir snapshot FSRS persistido.
- `/api/v1/mobile/progress` permanece compatível com clientes 0.13.x.

