# Relatório de validação — QuestFlow Studio 6.18.2

## Causa raiz
Na 6.18.1, seis funções de cobertura/documentação de trilhas foram removidas de `web/app.js`, porém referências a elas permaneceram em `bindEvents()`, `loadCoverage()` e no fluxo de startup. A primeira referência direta (`addTrailGuidePdfs`) gerava `ReferenceError` dentro de `bindEvents()` antes do bloco que inicializa a ponte HTTP e antes de `bridge.startHeartbeat()`.

Sintoma: a casca visual do Studio era exibida em “Carregando/Preparando interface”, mas o runtime encerrava a tentativa por ausência de heartbeat.

## Correção
Foram restauradas as funções:
- `trailLabel`
- `renderTrailGuideStatus`
- `notifyMissingTrailGuides`
- `addTrailGuidePdfs`
- `checkStudyGuideWatch`
- `startStudyGuideWatch`

Foi adicionado `tests/test_web_startup_symbols_6182.py` para impedir a regressão.

## Segurança
Nenhuma migração de banco e nenhuma mudança no Learning Engine. O hotfix é de interface/startup.
