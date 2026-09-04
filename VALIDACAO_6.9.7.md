# Validação — QuestFlow Studio 6.9.7 / Mobile 0.4

## Escopo

- triagem antes da resposta;
- correção de questão sem criar tentativa;
- backlog de assunto ainda não estudado;
- exclusão do conteúdo dos lotes enquanto pendente;
- liberação após estudo;
- compatibilidade com Mobile Foundation, ciclo de aparelhos e Cloud Bridge;
- preservação do Quality Gate de tempo e do histórico unificado.

## Testes específicos

`tests/test_mobile_study_triage_697.py` valida:

1. solicitação de correção entra na fila existente com origem Mobile e sem tentativa;
2. conteúdo “ainda não estudado” entra no backlog sem virar erro;
3. questões do mesmo assunto/aula deixam de ser selecionadas enquanto pendentes;
4. a ação “Já estudei” libera o conteúdo para novos lotes.

## Resultado de regressão

A suíte Python completa foi executada em quatro partições determinísticas por limite operacional do ambiente:

- partição 1: 126/126;
- partição 2: 107/107;
- partição 3: 118/118;
- partição 4: 136/136;
- total: **487/487 testes aprovados**.

Os testes críticos Mobile/Foundation/Cloud Bridge/Study Triage também foram executados em conjunto: **18/18 aprovados**.

## Checks de release

- `compileall`: OK;
- JavaScript (`node --check web/app.js`): OK;
- TypeScript alterado: sintaxe validada;
- `npm run test:core`: OK;
- `requirements.lock`: hash íntegro;
- smoke test: OK;
- SQLite `PRAGMA integrity_check`: `ok`;
- foreign keys: sem violações no smoke test;
- runtime: `6.9.7`;
- Mobile: `0.4.0`;
- SBOM: `SBOM_6.9.7.cdx.json`;
- matriz de compatibilidade: `MATRIZ_COMPATIBILIDADE_6.9.7.json`;
- auditoria automatizada de vulnerabilidades: registrada como indisponível porque `pip-audit` não está instalado no ambiente de empacotamento; não foi tratada como aprovação falsa.

## Contrato

- `questflow.mobile.v1` preservado;
- schema lógico v1 preservado;
- Mobile 0.4.0;
- novos eventos são aditivos e idempotentes;
- Cloud Bridge permanece compatível;
- HOTFIX1 de migração segura no Windows preservado.
