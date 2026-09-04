# Validação técnica — QuestFlow Studio 6.7.2

## Escopo

Validação do novo fluxo **Pesquisar resposta no Google com IA** e regressão da base 6.7.1.

## Resultado

- **392 / 392 testes automatizados aprovados**, executados em quatro partições: 90 + 91 + 107 + 104.
- **154 arquivos Python** compilados com sucesso.
- `web/app.js` aprovado pelo `node --check`.
- Método `start_google_commentary_research` presente na allowlist HTTP.
- Rota HTTP local real validada com POST `/api/call`.

## Casos específicos validados

- pesquisa retorna explicação e fontes sem persistir silenciosamente a questão;
- `Origem do comentário` é preparada como `ia_assistida` na interface;
- alterações ainda não salvas do editor entram como contexto da pesquisa;
- código da questão é priorizado na consulta quando permitido pela política de privacidade;
- divergência entre gabarito Google e gabarito local não sobrescreve o banco;
- modo de privacidade `private` bloqueia a operação Google;
- ausência de explicação verificável gera erro e não preenche o editor;
- interação fica como rascunho até decisão humana;
- Curadoria, Cloud Sync, Watchdog, Tutor, RAG, FSRS, KT, IRT e demais regressões permanecem verdes.

## Schemas

Nenhuma migração nova:

- `question_bank v8`
- `study v11`
- `ai_governance v4`
