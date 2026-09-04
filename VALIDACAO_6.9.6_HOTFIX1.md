# Validação 6.9.6 HOTFIX1 — Windows Update/Migration

## Escopo

Correção do fluxo de atualização quando a versão anterior falha na criação do
backup pré-update com `WinError 123` no Windows.

## Alterações validadas

- backup pré-update fora de `data/`, evitando recursão e reduzindo o caminho;
- fallback para diretório temporário gravável;
- migração segura para uma pasta nova;
- preservação da instalação anterior;
- `PRAGMA quick_check` antes do backup, no backup e após a migração;
- sobreposição apenas da árvore de dados na nova instalação, mantendo o código
  da release 6.9.6.

## Testes executados

- `py_compile` de `migrar_dados_versao_anterior.py` e `core/production_hardening.py`: OK;
- migração simulada 6.9.5 → 6.9.6 em diretórios temporários: OK;
- `PRAGMA quick_check` no banco migrado: `ok`;
- `tests.test_production_hardening_673`: 10/10 aprovados.

## Observação

O aplicativo continua reportando versão funcional `6.9.6`; HOTFIX1 identifica a
correção do empacotamento/atualizador para Windows.
