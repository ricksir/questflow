# Relatório de validação — QuestFlow Studio 6.16.1

## Problema corrigido

O workspace do Tutor recebia candidatos do banco com chaves `source_code` e `primary_topic`, mas a interface procurava prioritariamente `code` e `topic`. Quando `code` não existia, o JavaScript usava `uid` como fallback visual, expondo UUIDs internos ao usuário.

## Implementação

- `AIEngine.workspace()` agora publica um view-model explícito para candidatos do Tutor: `uid` interno + `code`, `subject`, `topic`, `lesson` e `statement` humanos.
- O frontend nunca usa UID como rótulo. Se uma questão realmente não possuir código público, mostra `Questão sem código visível`.
- Foi adicionada detecção defensiva de UUID para impedir regressão visual.
- O seletor exibe Código → Matéria → Assunto/Aula → trecho do enunciado.
- Foi adicionada busca textual por código, matéria, assunto, aula e enunciado.
- A microcopy explica ao usuário que a escolha serve para indicar qual questão ele quer entender e que o Tutor usa o histórico para orientar a revisão.

## Testes executados

- 65 testes direcionados/regressão: aprovados.
- Falhas funcionais: 0.
- `node --check web/app.js`: aprovado.
- Tutor AI / seis motores / scaffolding: aprovados.
- Runtime/watchdog e production hardening: aprovados.
- Retrieval observability e quality gates: aprovados.
- Mobile Study Only 0.11.0: regressão aprovada; nenhum código Mobile alterado.
- Atualizador Windows / preservação de `mobile` e `data`: testes aprovados.

## Banco real fornecido no pacote-base

- Questões antes de abrir com a release atual: 1.292.
- Questões após inicialização/migrações não destrutivas: 1.292.
- `PRAGMA quick_check`: `ok`.
- `PRAGMA foreign_key_check`: 0 violações.
- A 6.16.1 não adiciona migração de schema.

## Impacto

- SQLite: nenhum impacto estrutural.
- Learning Engine: nenhum impacto.
- FSRS/KT/IRT/Learner State: nenhum impacto.
- Turso/Cloud Sync: nenhum impacto.
- Mobile: permanece 0.11.0.

## Limitação de ambiente

Não havia automação de navegador Windows disponível neste ambiente; a UX foi validada por inspeção estrutural, testes unitários e validação sintática do JavaScript.
