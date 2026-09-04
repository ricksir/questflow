# QuestFlow Mobile API v1 — fronteira Study Only 6.12.2

O contrato continua `questflow.mobile.v1`, porém a superfície Mobile é restrita ao estudo.

## Regra

A API Mobile não expõe controles de canais operacionais. Telegram é configurado e controlado exclusivamente pelo QuestFlow Studio.

Foi removido:

```http
/api/v1/mobile/channels/telegram
```

Também foram removidos dos payloads Mobile:

- `bootstrap.channels`;
- `today.channels`;
- `progress.summary.channels`;
- `recent_activity[].channel`.

As métricas pedagógicas continuam agregando todo o histórico válido do aluno, independentemente da origem interna do registro. A origem operacional não integra o contrato do aplicativo.

## Endpoints principais

- `GET /api/v1/mobile/health`
- `POST /api/v1/mobile/pairing/exchange`
- `GET /api/v1/mobile/bootstrap`
- `GET /api/v1/mobile/today`
- `GET /api/v1/mobile/priorities`
- `GET /api/v1/mobile/progress`
- `POST /api/v1/mobile/question-batches`
- `GET /api/v1/mobile/questions/{question_id}`
- `GET /api/v1/mobile/attempts/{attempt_id}/feedback`
- `POST /api/v1/mobile/sync`
- `POST /api/v1/mobile/devices/push-token`
- `DELETE /api/v1/mobile/devices/{device_id}`

Ações de Telegram, infraestrutura, Saúde da IA, Retrieval Health e administração não fazem parte desta API.
