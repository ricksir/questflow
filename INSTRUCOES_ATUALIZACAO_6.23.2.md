# Atualização QuestFlow Studio 6.23.2

1. Feche completamente o QuestFlow Studio.
2. Abra `C:\Users\user\QuestFlow\QUESTFLOW.bat`.
3. Escolha **Atualizar QuestFlow**.
4. Selecione `QuestFlow_Studio_6.23.2_UPDATE.zip` e aguarde o Manager concluir backup, staging e smoke test.
5. Abra o Studio e confirme **Versão 6.23.2**.
6. No Manager, escolha **[8] Ativar início automático do Studio com o Windows** uma única vez.

O Mobile permanece na versão 0.15.6; não é necessário reinstalar o APK. O Manager preserva `data`, SQLite, configurações, credenciais, ambientes Python, runtime e backups.

Depois da atualização, uma suspensão ou hibernação longa não será interpretada como fechamento da janela. O Studio aguardará o Chrome retomar e relançará apenas a interface se necessário, mantendo backend e comunicação Mobile ativos. A opção [8] cobre também reinicializações completas do Windows.
