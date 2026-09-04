# QuestFlow Mobile API v1 — extensões 6.10.0

O contrato continua `questflow.mobile.v1`. A 6.10.0 amplia `POST /api/v1/mobile/question-batches` de forma retrocompatível.

## Criar lote de sessão

```json
{
  "count": 10,
  "exam_project_id": "",
  "mode": "recommended",
  "subject": ""
}
```

`mode` aceita:

- `recommended`: prioridade pedagógica normal do QuestFlow;
- `review`: apenas questões com revisão devida;
- `errors`: questões com histórico de erro;
- `subject`: apenas a matéria informada em `subject`.

Clientes antigos que enviarem apenas `count` continuam recebendo o lote `recommended`.

Cada questão pode incluir `study_flags` com sinais seguros para o cache/offline:

```json
{
  "study_flags": {
    "due": true,
    "wrong_count": 2,
    "sent_count": 5
  }
}
```

Esses campos não incluem gabarito, alternativa correta ou comentário privado.

## Sessões interrompidas

A persistência do ponto de retomada é responsabilidade do cliente oficial e fica no SQLite local do aparelho. O servidor recebe `session_started` e `session_ended`, preservando o contrato de eventos existente.
