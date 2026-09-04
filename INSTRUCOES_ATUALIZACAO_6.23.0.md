# Atualização QuestFlow Studio 6.23.0 + Mobile 0.15.5

1. Feche completamente o QuestFlow Studio.
2. Abra `C:\Users\user\QuestFlow\QUESTFLOW.bat`.
3. Escolha **Atualizar QuestFlow**.
4. Selecione `QuestFlow_Studio_6.23.0_UPDATE.zip` e aguarde o Manager concluir backup, staging e smoke test.
5. Abra o Studio e confirme **Versão 6.23.0**.
6. Se desejar usar a fonte externa, abra **Configurações → Fonte do catálogo de questões**, informe a API Key da APIdasQuestões, teste e salve.

O Manager preserva `data`, SQLite, configurações locais, credenciais, ambientes Python, runtime e backups. A migração é somente aditiva e possui rollback automático em caso de falha.

O Mobile permanece em `0.15.5` e não precisa ser reinstalado.
