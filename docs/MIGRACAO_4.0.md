# Migração para o QuestFlow Studio 4.0

1. Feche todas as versões do QuestFlow.
2. Extraia o ZIP 4.0.0 em uma pasta nova.
3. Copie da pasta antiga para `data` da versão nova:
   - `questflow_questions.sqlite`;
   - `config.json`;
   - `question_images`;
   - `markdown_cache`, se existir;
   - `google_browser_profile`, se existir.
4. Não copie `.venv` nem substitua `taxonomia_afrfb.json` pela versão antiga.
5. Execute `INSTALAR_E_DIAGNOSTICAR.bat`.
6. Abra `INICIAR_QUESTFLOW_STUDIO.bat`.

As novas colunas do motor adaptativo são criadas automaticamente. Questões, respostas, correções, histórico e imagens permanecem no mesmo banco.

## Explicações no Telegram

Em **Fluxo Telegram**, escolha:

- `Explicação completa após responder`;
- `Resultado curto + botão de explicação`;
- `Somente pelo botão Ver explicação`.

A primeira opção é recomendada quando você quer revisar imediatamente.
