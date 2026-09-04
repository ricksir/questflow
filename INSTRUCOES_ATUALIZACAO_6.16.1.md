# QuestFlow Studio 6.16.1 — Instruções de atualização

## O que esta versão corrige

Na tela **Tutor IA → Questão para analisar**, o seletor podia mostrar o UUID interno da questão. A 6.16.1 mantém esse identificador apenas no backend e passa a mostrar ao usuário **código, matéria, assunto/aula e início do enunciado**.

Também foi adicionada uma busca por **código, matéria, assunto, aula ou trecho do enunciado**.

## Como atualizar

1. Feche o QuestFlow Studio.
2. Abra o atualizador normal do QuestFlow.
3. Selecione `QuestFlow_Studio_6.16.1_UPDATE.zip`.
4. Aguarde backup, validação e conclusão do update.
5. Abra o Studio e confira **Tutor IA → Qual questão você quer entender?**.

## Resultado esperado

Em vez de uma chave como `9f96ae14-37aa-42d3-be10-a087261ebf05`, a opção passa a ter formato semelhante a:

`Q2015460 — AUDITORIA — AUDITORIA INTERNA / TÓPICOS COMPLEMENTARES — Considerando as normas brasileiras...`

O UUID continua existindo apenas como chave interna e não é mostrado como identidade da questão.

## Impactos

- Banco SQLite: nenhuma migração.
- Learning Engine: nenhuma alteração.
- Cloud Sync/Turso: nenhuma alteração.
- Mobile: permanece 0.11.0 e não precisa ser atualizado.
