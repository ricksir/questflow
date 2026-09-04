# Atualização QuestFlow Studio 6.22.11 + Mobile 0.15.2

## Studio

1. Feche o Studio, o Manager e terminais relacionados ao QuestFlow.
2. Extraia `QuestFlow_Studio_6.22.11_UPDATE.zip` para uma pasta temporária.
3. Abra a pasta `QuestFlow` extraída.
4. Execute `ATUALIZAR_QUESTFLOW_SEGURO.bat` e confirme a atualização `6.22.10 → 6.22.11`.
5. Aguarde o backup, a aplicação e a validação terminarem.
6. Abra o Studio e confirme `Versão 6.22.11`.

O banco, as respostas, o histórico, o pareamento, o runtime e os backups são preservados.

## Android

1. Copie `QuestFlow_Mobile_0.15.2.apk` para o telefone.
2. Abra o APK e escolha **Atualizar**. Não desinstale a versão 0.15.1: a atualização preserva os dados locais.
3. Confirme `QuestFlow Mobile 0.15.2` na tela de pareamento ou em **Perfil**.
4. Em **Perfil → Lembretes de estudo**, toque em **Ativar lembrete diário** e conceda a permissão de notificações.

O lembrete é agendado localmente para 19h e não depende de Firebase, internet ou do Studio aberto. O pareamento agora abre com o QR como ação principal; endereço e token ficam em uma alternativa manual recolhível.
