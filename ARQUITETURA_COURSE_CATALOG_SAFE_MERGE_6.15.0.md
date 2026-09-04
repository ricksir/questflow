# Arquitetura — QuestFlow Studio 6.15.0

## Objetivo

A versão 6.15.0 separa a estrutura do curso do estado pedagógico do aluno para permitir trocar a planilha de trilhas sem apagar conhecimento já adquirido pelo QuestFlow.

## Camadas

### Course Catalog

Fonte estrutural proveniente da planilha Google/XLSX. Mantém trilha, tarefa, aula, matéria, título, descrição, carga horária e metadados estruturais. O catálogo é versionado e auditável no SQLite.

Tabelas novas:

- `course_catalog_lessons`
- `course_catalog_imports`
- `course_catalog_changes`

### Learner State

Estado pessoal durável do aluno. A planilha deixa de ser fonte absoluta desse estado. A camada nova `course_learner_state` preserva evidências legadas de aula estudada, data, tempo efetivo, questões e acertos, enquanto FSRS, KT, IRT, learner model, XP, sessões e demais estados continuam nas tabelas existentes do Learning Engine.

### Safe Merge

`core/course_catalog.py` implementa `incremental-preserve-progress-v1`.

Fluxo:

1. baixar/importar a nova planilha em modo somente leitura;
2. validar schema e abas reconhecidas;
3. criar identidade estável da aula por `Trilha + Tarefa + Aula + Disciplina`, normalizada;
4. executar preflight/dry-run sem gravar progresso;
5. bloquear correspondências incertas até decisão humana;
6. criar backup SQLite, SHA-256, `PRAGMA quick_check` e `foreign_key_check`;
7. aplicar catálogo em transação;
8. mesclar progresso monotonicamente: vazio novo nunca reduz estado antigo;
9. arquivar aulas ausentes sem apagar histórico;
10. validar banco; somente então trocar a URL ativa;
11. em falha, restaurar banco/configuração/taxonomia anterior.

## Integração com Learning Engine

`StudyRepository.refresh_studied_scope()` foi alterado para não tratar a planilha como fonte absoluta do que foi estudado. O estado durável do catálogo/learner state é combinado ao escopo existente e novas aulas permanecem não estudadas.

Não foi criado Learning Engine paralelo. FSRS, Knowledge Tracing, IRT, learner model, Adaptive Session Orchestrator e demais motores existentes continuam sendo as fontes pedagógicas canônicas.

## Cloud Sync

Mudanças de catálogo são classificadas como `content.*`. O Learner State não é reenviado em massa por uma troca de catálogo. A lógica de sincronismo preserva as proteções existentes contra `last-write-wins` indevido em estado pedagógico.

## Mobile

Mobile permanece em 0.10.1 e Study Only. Não recebe URL, nome da planilha, preflight, conflitos nem metadados de importação. Ele consome apenas o estado consolidado do QuestFlow.

## UI clássica

A funcionalidade foi extraída para `ui/catalog_settings_mixin.py`, mantendo `ui/settings_export_mixin.py` abaixo do limite arquitetural de 1.000 linhas. A interface oferece teste, dry-run, filtros de diferenças, resolução humana e relatório pós-mesclagem.
