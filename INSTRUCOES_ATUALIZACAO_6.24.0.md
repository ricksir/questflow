# Atualização QuestFlow Studio 6.24.0 + Mobile 0.16.0

## Studio

1. Feche completamente o QuestFlow Studio.
2. Abra `C:\Users\user\QuestFlow\QUESTFLOW.bat`.
3. Escolha **Atualizar QuestFlow**.
4. Selecione `QuestFlow_Studio_6.24.0_UPDATE.zip` e aguarde o Manager concluir backup, staging e smoke test.
5. Abra o Studio e confirme **Versão 6.24.0** no menu lateral.

O Manager preserva `data`, o banco SQLite, configurações, credenciais, ambientes Python, runtime e backups.

## Mobile

1. Copie `QuestFlow_Mobile_0.16.0.apk` para o celular.
2. Abra o APK e confirme a atualização do aplicativo existente.
3. Se o Android bloquear a instalação, autorize temporariamente a origem usada para abrir o APK.
4. Abra o aplicativo e confirme **v0.16.0** em **Perfil > Acessibilidade e versão**.
5. No Studio, abra **QuestFlow Mobile**, selecione **Conectar novo aparelho** e leia o QR Code.

Não desinstale o aplicativo antes da atualização: a instalação por cima preserva os dados locais e a sessão offline.

## Conferência rápida

- Em **Visão geral**, a área **Prioridade por matéria** deve mostrar até seis cartões e permitir abrir os detalhes de cada matéria.
- Em **Progresso** no Mobile, a lista deve mostrar cinco matérias inicialmente e oferecer **Mostrar mais** quando houver outras.
- Em **Hoje**, o roteiro da sessão deve apresentar as etapas Recuperar, Intercalar e Consolidar usando os dados reais disponíveis.

