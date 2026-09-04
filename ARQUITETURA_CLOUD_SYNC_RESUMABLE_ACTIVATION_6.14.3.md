# QuestFlow 6.14.3 — Cloud Sync Resumable Activation

## Problema corrigido

A ativação segura introduzida na 6.14.1/6.14.2 drenava a outbox com `sync_until_idle(max_rounds=10)`. Como cada `sync_once()` envia no máximo 250 eventos, a primeira sincronização possuía teto matemático de 2.500 eventos por tentativa. Filas maiores eram classificadas como falha mesmo quando Turso, SQLite e idempotência estavam saudáveis.

## Regra nova

A primeira ativação é tratada como workflow retomável:

```text
preflight -> backup -> pull/merge -> seed uma vez -> sync slice ->
  pending > 0: checkpoint progress -> próximo slice
  pending = 0 e conflicts = 0: active
  erro real: failed/retry-safe
```

Cada slice continua limitado para preservar responsividade e evitar uma chamada de rede sem limite. O frontend repete slices enquanto houver progresso e mostra o número restante.

## Proteção contra duplicação

`activation_seeded_at` e `activation_checkpoint` registram que a fotografia inicial já foi preparada. Uma retomada não chama `enqueue_full_snapshot()` novamente.

Há compatibilidade explícita com o erro genérico da 6.14.2 (`first_sync_failed` + backup + mensagem de fila incompleta), permitindo continuar a tentativa real que já escreveu parte dos eventos no Turso.

## Segurança

- automático só é ligado quando `pending=0` e `conflicts=0`;
- falhas de rede mantêm ativação incompleta;
- eventos confirmados permanecem protegidos por `event_id` remoto único;
- backup pré-primeira-escrita é preservado;
- nenhuma alteração no contrato Mobile ou nas métricas pedagógicas.
