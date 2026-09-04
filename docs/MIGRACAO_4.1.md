# Migração para 4.1.0

1. Feche todas as versões do QuestFlow.
2. Extraia a pasta 4.1.0 em um novo local.
3. Copie para `data/`:
   - `questflow_questions.sqlite`;
   - `config.json`;
   - `question_images/`;
   - `markdown_cache/`;
   - `google_browser_profile/`.
4. Não copie `.venv`.
5. Não substitua `taxonomia_afrfb.json` pela versão antiga.
6. Execute `INSTALAR_E_DIAGNOSTICAR.bat`.

Na primeira abertura, o banco recebe automaticamente:

- campos FSRS por questão;
- tabela de estado por assunto;
- perfil de XP/nível;
- eventos de XP.

A migração é aditiva e não remove questões nem histórico.
