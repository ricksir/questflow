# Atualização QuestFlow 6.16.0 + Mobile 0.11.0

1. Feche QuestFlow Studio e o Mobile/Metro.
2. Instale `QuestFlow_Studio_6.16.0_UPDATE.zip` pelo atualizador seguro normal.
3. Abra o QuestFlow e confirme Studio 6.16.0.
4. Feche o Mobile/Metro e execute `ATUALIZAR_QUESTFLOW_MOBILE_0.11.0.bat` na pasta do QuestFlow. O script preserva `mobile/node_modules` e `mobile/.expo`.
5. Para testes conectados com Expo Dev Client, inicie o Mobile normalmente.
6. Para garantir abertura sem Studio, sem Metro e sem internet, gere e instale um build Preview Android com `GERAR_APK_MOBILE_0.11.0_EAS.bat` (a geração requer internet uma única vez).
7. Com Studio e celular conectados, use Sincronizar. A tela Questões deverá mostrar `Reserva Offline` com a quantidade disponível.
8. Depois disso, desligue Wi-Fi/dados e feche o Studio. Abra o build Preview/Production e inicie uma sessão. As respostas ficarão locais até a conexão retornar.

## Como usar o risco de alternativa

Na etapa Responder, arraste uma alternativa horizontalmente para a esquerda ou para a direita. O texto ficará riscado. Repita o gesto para desfazer. Se tocar numa alternativa riscada para selecioná-la, o risco é removido automaticamente.

## Importante

A Reserva Offline não contém gabarito. Offline, o botão `Continuar offline — próxima questão` salva a resposta e avança. Ao sincronizar, o Studio corrige, atualiza o Learner State e prepara uma nova Reserva Offline.
