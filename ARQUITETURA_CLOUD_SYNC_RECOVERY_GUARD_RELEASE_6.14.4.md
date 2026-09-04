# QuestFlow 6.14.4 — Safe Activation + Recovery Guard

## Problema corrigido

Após uma recuperação de dados, `RECOVERY_GUARD.json` existe para impedir que o Cloud Sync automático reaplique um estado remoto antes de uma reconciliação humana. Na 6.14.3, a Ativação segura chamava `sync_until_idle(force=True)`, mas `sync_once()` continuava bloqueando qualquer escrita quando o guard estava presente. Como o bloqueio retornava `disabled` sem `error`, a camada de ativação podia classificar um ciclo de zero envios como “em progresso”.

Sintoma: fila permanece exatamente com a mesma quantidade após `Retomar primeira sincronização`.

## Nova regra

A **Ativação segura** é a reconciliação explícita aguardada pelo Recovery Guard.

1. preflight somente leitura;
2. valida SQLite/Turso;
3. cria e valida backup SQLite;
4. se houver `RECOVERY_GUARD.json`, arquiva uma cópia íntegra em `data/cloud_sync_backups/RECOVERY_GUARD.released-<timestamp>.json`;
5. valida SHA-256 do arquivo arquivado;
6. remove somente o guard ativo;
7. mantém `activation_state != active`, portanto sincronismo automático continua bloqueado;
8. retoma a outbox existente sem nova semeadura;
9. só libera automático quando `pending = 0` e `conflicts = 0`.

## Auditoria

O runtime registra:

- `activation_recovery_guard_released_at`;
- `activation_recovery_guard_archive`;
- `activation_recovery_guard_sha256`.

O guard não é simplesmente apagado: sua cópia auditável permanece no backup do Cloud Sync.

## Proteção contra falso progresso

`sync_until_idle()` agora propaga estados `disabled`/`recovery_guard` como bloqueio acionável. A ativação também verifica progresso real: se `pending` não diminuir e `pushed == 0`, o ciclo não é apresentado como avanço.
