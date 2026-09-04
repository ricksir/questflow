# Relatório de validação — QuestFlow Studio 6.15.0

## Resultado

**Release funcionalmente aprovada para UPDATE incremental da 6.14.4 para 6.15.0 no ambiente validado.**

## Testes automatizados

- 573 testes pytest aprovados.
- 10 subtests aprovados.
- 0 assertions falhas.
- Testes específicos da troca de catálogo cobrem cenários A–I, idempotência, rollback e resolução humana de ambiguidades.
- Teste arquitetural aprovado após extração de `CatalogSettingsMixin`.

A suíte monolítica apresentou travamento de encerramento de processos auxiliares no ambiente Linux. Para evitar falso timeout, os arquivos foram executados de forma isolada e a parte restante em um processo pytest com encerramento explícito; todos os 573 testes coletados foram efetivamente executados e aprovados.

## Smoke e integridade

- `compileall`: aprovado.
- import da versão: 6.15.0.
- `PRAGMA quick_check`: `ok`.
- `PRAGMA foreign_key_check`: 0 violações.
- Node/web syntax: coberta pelos testes existentes; o smoke principal passou.

## Simulação do atualizador 6.14.4 → 6.15.0

Executada com `questflow_update_runner.py` da instalação 6.14.4 sobre cópia do pacote fornecido.

- versão inicial: 6.14.4;
- versão final: 6.15.0;
- backup pré-update: criado e validado;
- smoke em staging: aprovado;
- smoke pós-instalação: aprovado;
- teste de restauração: aprovado;
- rollback: não necessário;
- SHA-256 do SQLite antes/depois da instalação: idêntico;
- banco principal: 1.292 questões preservadas.

Após inicialização da 6.15.0 e migração de schema:

- `questions`: 1.292 → 1.292, hash lógico igual;
- `study_state`: 1.292 → 1.292, hash lógico igual;
- `lesson_learning_state`: 8 → 8, hash lógico igual;
- `topic_learning_state`: 8 → 8, hash lógico igual;
- `question_irt`: 8 → 8, hash lógico igual;
- `learner_profile`: 1 → 1, hash lógico igual;
- `learner_model_events`: 18 → 18, hash lógico igual;
- `adaptive_model_state`: 1 → 1, hash lógico igual;
- `xp_events`: 18 → 18, hash lógico igual;
- `study_cycles`: 1 → 1, hash lógico igual;
- `telegram_attempts`: 18 → 18, hash lógico igual;
- sessões/eventos Mobile protegidos: contagem e hash lógico iguais;
- `studied_scope`: 39 → 39; chaves lógicas iguais. Apenas `updated_at` foi renovado pela rotina normal de refresh.

## Simulação da troca de catálogo sobre cópia do banco real

Foi usado o catálogo real atual com uma expansão sintética de 9 novas aulas e os campos pessoais antigos removidos da nova entrada para simular uma planilha atualizada vazia nesses campos.

- aulas correspondentes: 473;
- aulas novas: 9;
- progresso preservado: 39;
- campos pessoais sobrescritos por vazio: 0;
- novas aulas marcadas como não estudadas: 100%;
- `studied_scope`: 39 antes / 39 depois;
- `questions`, `study_state`, Telegram, KT, adaptive model, XP e learner profile: hashes lógicos inalterados;
- quick_check: ok;
- foreign keys: 0.

## Migrações realizadas

Migração aditiva e não destrutiva para criar:

- `course_catalog_lessons`;
- `course_learner_state`;
- `course_catalog_imports`;
- `course_catalog_changes`;
- índices auxiliares.

Nenhuma tabela pedagógica existente foi removida ou reconstruída.

## Impacto no banco

A atualização de código não modifica o banco durante a instalação. Na primeira inicialização, apenas o schema aditivo acima é criado. O conteúdo do catálogo é populado quando uma planilha é efetivamente mesclada.

## Impacto no Mobile

Nenhum. Mobile permanece 0.10.1 e não foi incluído no UPDATE.

## Impacto no Cloud Sync

Mudanças de catálogo são tratadas como conteúdo; não há ressincronização integral do Learner State pela simples troca da planilha. Estados pedagógicos protegidos continuam fora de `last-write-wins` indiscriminado.

## Testes não executados / limitações

- Python 3.11, 3.12 e 3.14 não estavam instalados neste ambiente; a matriz registra-os como não disponíveis. Python 3.13.5 foi validado.
- A planilha real Trilhas 00–27 não foi fornecida. O comportamento 00–27 foi validado por testes automatizados e por uma expansão sintética sobre a taxonomia/banco reais.
- `pip-audit` não estava instalado; a auditoria de vulnerabilidades ficou com status `unavailable` (não estrito). O SBOM CycloneDX foi gerado normalmente.
- Interfaces gráficas foram validadas por testes automatizados/smoke; não houve interação manual em Windows nesta execução Linux.
