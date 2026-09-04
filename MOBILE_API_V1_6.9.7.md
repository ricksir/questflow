# QuestFlow Mobile API v1 — Studio 6.9.7 / Mobile 0.4

O contrato permanece `questflow.mobile.v1` e o schema lógico continua versão 1. A 6.9.7 é uma evolução aditiva de eventos e projeções.

## Novos eventos de triagem antes da resposta

### `question_correction_requested`

Usado quando o aluno identifica que a própria questão precisa de correção antes de respondê-la.

Efeito no Studio:

- cria ou reativa uma solicitação na fila de correções existente;
- origem registrada como `mobile_preanswer`;
- suspende a questão até revisão humana;
- não cria tentativa de desempenho;
- não altera acerto, erro, FSRS, KT, IRT ou tempo de resposta.

### `topic_not_studied_reported`

Registra que o conteúdo ainda não foi estudado.

O Studio cria um backlog por combinação de matéria, assunto e aula. Enquanto o item estiver `pending`, questões do mesmo conteúdo deixam de ser selecionadas nos lotes Mobile.

A marcação não é tratada como resposta e não entra nas métricas de desempenho.

### `topic_study_completed`

Marca um item do backlog como estudado e libera novamente o conteúdo para futuras sessões de questões.

## Projeção de progresso

`GET /api/v1/mobile/progress` passa a incluir:

```json
{
  "study_backlog": {
    "pending_count": 1,
    "items": [
      {
        "backlog_id": "...",
        "topic_key": "...",
        "subject": "Direito Administrativo",
        "topic": "Atos administrativos",
        "lesson": "Aula 01",
        "mark_count": 1
      }
    ]
  }
}
```

## Projeção Hoje

`GET /api/v1/mobile/today` passa a informar `today.not_studied_topics`.

## Offline e Cloud Bridge

Os três novos eventos usam a mesma outbox idempotente já existente. O Gateway Cloud apenas transporta os eventos; a aplicação definitiva dos efeitos continua sendo feita pelo Studio.

O cliente mantém bloqueio local de questões/assuntos marcados para evitar reaparecimento durante períodos offline antes do próximo `publish` do Studio.
