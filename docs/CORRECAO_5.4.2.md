# QuestFlow Studio 5.4.2 — correção do diagnóstico Cloud Sync no Windows

## Sintoma
O instalador podia encerrar com `WinError 32` ao remover `cloud-test.sqlite`, embora o teste de Cloud Sync tivesse sido concluído corretamente.

## Causa
`sqlite3.Connection` usado diretamente como context manager confirma/desfaz a transação, mas **não fecha** a conexão ao sair do bloco. Em Windows, o handle permanecia aberto até o fim de `diagnostico.py`, enquanto `TemporaryDirectory` tentava apagar o arquivo imediatamente. Linux permite remover arquivo aberto e, por isso, a falha não aparecia nos testes anteriores.

## Correção
- `diagnostico.py` usa `contextlib.closing(sqlite3.connect(...))` para liberar o handle antes do cleanup;
- executa `PRAGMA wal_checkpoint(TRUNCATE)` antes da remoção;
- adiciona teste de regressão que proíbe o padrão não-fechável no diagnóstico;
- nenhuma alteração é feita no banco de questões do usuário ou nas credenciais Turso.
