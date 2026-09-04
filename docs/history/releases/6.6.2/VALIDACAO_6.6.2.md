# Validação técnica — QuestFlow Studio 6.6.2

## Falha reproduzida

Foi reproduzido o ciclo relatado pelo usuário com exatamente **213 questões candidatas**:

| Etapa | 6.6.1 original | 6.6.2 corrigida |
|---|---:|---:|
| Após sincronizar | 0 pendências | 0 pendências |
| Após atualizar Recomendador/painel | 213 | 0 |
| Grupo criado | `study_state` | nenhum |

A origem era `_auditor_intelligent_selection()`, que persistia métricas derivadas durante uma pré-visualização.

## Correções

- `LearningEngine.recommendation_dashboard()` usa `select_questions(..., persist_state=False)`.
- `StudyRepository.select_questions()` ganhou modo explícito read-only.
- `_auditor_intelligent_selection()` e `_select_status_tier()` propagam `persist_state`.
- O trigger `qf_sync_study_state_au` ignora alterações somente nos campos transitórios:
  `memory_retrievability`, `adaptive_prediction`, `adaptive_priority`, `last_selection_reason`, `last_selection_bucket`.
- UPDATEs sem alteração efetiva também não geram evento.
- Campos duráveis continuam gerando outbox normalmente.

## Testes novos

`tests/test_cloud_sync_refresh_662.py` valida:

1. update transitório não entra na outbox;
2. update durável continua entrando;
3. preview do Recomendador após sync permanece read-only;
4. seleção operacional pode persistir score transitório sem ruído de sync.

## Regressão

A suíte foi executada em três grupos:

- 131 testes: OK
- 124 testes: OK
- 86 testes: OK

**Total: 341/341 aprovados.**

Também passaram:

- `py_compile` dos módulos alterados;
- `node --check web/app.js`;
- regressões históricas de Cloud Sync;
- convergência entre dois dispositivos;
- offline/outbox durável;
- reset por geração;
- diagnósticos da 6.5.2;
- FSRS 6;
- Learner Model/KT/IRT;
- Recomendador e simulados adaptativos;
- Projeto de Concurso/Edital;
- safe close e integridade SQLite.

Os `ResourceWarning` de testes legados permanecem avisos não bloqueantes e não produziram falhas.
