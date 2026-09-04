# Validação — QuestFlow Studio 6.8.0 Hotfix 2

## Problema reproduzido

O fluxo podia permanecer em “Pesquisando...” quando a resposta do Google era curta e não repetia o código público da questão, comportamento coerente com a própria diretiva da 6.8.0.

## Correções validadas

- resposta focada estabiliza sem ecoar `Qxxxx`;
- resposta útil não é reenviada apenas por `ai_answer_stable=false`;
- contingência por Google Web aceita apenas página pública aberta e correspondência verificada;
- progresso de etapa é enviado ao task monitor da interface;
- campo de explicação continua protegido contra texto geral/ruído;
- gabarito persistido não é alterado pela pesquisa.

## Testes

- Google/IA focado: **23/23**;
- regressão completa em quatro partições: **415/415**;
- partições: **111 + 101 + 106 + 97**.

## Schemas

Sem nova migração:

- `question_bank v8`
- `study v11`
- `ai_governance v4`
