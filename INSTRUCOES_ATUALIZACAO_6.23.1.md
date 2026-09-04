# Atualização QuestFlow Studio 6.23.1 + Mobile 0.15.6

1. Feche completamente o QuestFlow Studio.
2. Abra `C:\Users\user\QuestFlow\QUESTFLOW.bat`.
3. Escolha **Atualizar QuestFlow**.
4. Selecione `QuestFlow_Studio_6.23.1_UPDATE.zip` e aguarde o Manager concluir backup, staging e smoke test.
5. Abra o Studio e confirme **Versão 6.23.1**.
6. No telefone, abra `QuestFlow_Mobile_0.15.6.apk` e escolha **Atualizar**. Não desinstale a versão anterior.
7. No Mobile, abra **Perfil** e confirme **v0.15.6**.

O Manager preserva `data`, SQLite, configurações, credenciais, ambientes Python, runtime e backups. O APK usa o mesmo pacote Android (`br.questflow.mobile`) e `versionCode` 21, preservando o pareamento e os dados locais ao atualizar por cima da versão 0.15.5.
