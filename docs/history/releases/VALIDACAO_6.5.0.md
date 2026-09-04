# Validação técnica — QuestFlow Studio 6.5.0

## Resultado

**314 / 314 testes automatizados aprovados.**

A suíte integral foi executada após a integração final do estado temporal na inteligência individual da questão. Os `ResourceWarning` legados de conexões/sockets de testes continuam aparecendo como avisos, sem falhas funcionais.

## Escopo validado

- Projeto de concurso e projeto ativo.
- Registro do edital inicial e retificações.
- Diff de itens adicionados, removidos e alterados.
- Parser conservador do conteúdo programático.
- Mapeamento automático questão ↔ item do edital.
- Cobertura, estudo, domínio KT e prioridade por item.
- Central **O que fazer hoje?**.
- Precedência FSRS preservada.
- Estados temporais de questões.
- Exclusão segura de desatualizadas/anuladas/controversas da seleção normal futura.
- Preservação do histórico e do Banco Editorial.
- Varredura temporal com legislação versionada.
- Turso Cloud Sync dos novos dados editoriais.
- Allowlist e API HTTP local.
- Exatamente seis motores.

## Migração real 6.4.1 → 6.5.0

Foi criada uma base pela versão **6.4.1 original**, com 3 questões e 1 tentativa, e posteriormente aberta pela 6.5.0.

Resultado:

- questões antes/depois: **3 / 3**;
- tentativas antes/depois: **1 / 1**;
- `question_bank` avançou de **v7 para v8**;
- `PRAGMA quick_check`: **ok**;
- `PRAGMA foreign_key_check`: **0 violações**;
- projeto criado e ativado após a migração;
- 3 questões existentes foram mapeadas ao conteúdo de teste;
- Central Hoje respondeu usando o projeto migrado;
- arquitetura continuou com **6 motores**.

## Smoke test HTTP real

Foram chamadas pela mesma rota local usada pelo frontend:

- `save_exam_project`;
- `add_edital_version`;
- `get_today_dashboard`;
- `get_exam_project_dashboard`.

Todas responderam com sucesso. Também foram confirmados os triggers de Cloud Sync para projeto, versões, itens, vínculos e atualidade.

## Banco e schemas

- `question_bank`: **v8**
- `study`: **v9**
- `ai_governance`: **v2**

## Motores

1. Banco Editorial — `qf-editorial-engine-3`
2. Learner Model — `qf-learner-engine-1`
3. Learning Engine — `qf-learning-engine-3`
4. Knowledge Engine — `qf-knowledge-engine-2`
5. AI Engine — `qf-ai-engine-2`
6. Evaluation & Governance — `qf-ai-governance-2`

## Segurança da seleção

O status temporal não apaga questões. Questões `desatualizada`, `anulada` e `controversa` são removidas somente da seleção normal futura até decisão editorial; tentativas e dados históricos permanecem preservados.
