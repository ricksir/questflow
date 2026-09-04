# Validação — QuestFlow Studio 5.4.2

Correção direcionada ao `WinError 32` observado no diagnóstico Cloud Sync/Turso em Windows.

## Causa confirmada
O bloco de integridade usava `with sqlite3.connect(...) as check:`. O context manager nativo do `sqlite3` encerra a transação, mas não fecha a conexão. No Windows o arquivo `cloud-test.sqlite` permanecia com handle aberto enquanto `TemporaryDirectory` tentava removê-lo.

## Correção
- `contextlib.closing(sqlite3.connect(...))` garante `close()` antes do cleanup;
- `PRAGMA wal_checkpoint(TRUNCATE)` antes da remoção do banco temporário;
- teste estático de regressão impede reintroduzir o padrão não-fechável em `diagnostico.py`.

## Testes
- suíte completa: 182 testes aprovados;
- testes Cloud Sync, desligamento abrupto e instância fantasma: aprovados;
- diagnóstico local completo: concluído sem falhas;
- `PRAGMA integrity_check`: ok durante o autoteste Cloud Sync.

A correção não modifica o banco de questões nem credenciais Turso do usuário.
