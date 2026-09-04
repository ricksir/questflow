# QuestFlow Mobile 0.15.6 — avanço imediato e rotação entre blocos

Cliente Expo do QuestFlow Studio 6.18.0.

O Mobile apresenta apenas informações e ações diretamente relacionadas ao estudo: Hoje, Questões, Progresso, projeto, revisões, lembretes, salvamento do progresso e conta do aparelho.

Telegram, Saúde da IA, saúde do programa, arquitetura, serviços, endpoints, rotas, sincronismo técnico e diagnósticos ficam exclusivamente no QuestFlow Studio. O histórico pedagógico pode consolidar respostas registradas por diferentes origens, mas o aplicativo não expõe nem controla os canais técnicos que as produziram.


## 0.13.1 — cockpit adaptativo e consistência visual

- ações primárias em laranja e tendências em ciano, alinhadas ao Studio;
- anel acessível de desempenho e micrográficos comparativos em Hoje e Progresso;
- hierarquia “próxima ação → evidência → tendência → detalhe”, sem alterar o contrato offline.

## 0.13.0 — offline estrito e eliminação visual reforçada

- Reserva Offline aceita somente questões nunca respondidas ou questões cujo espaçamento do Studio já venceu.
- Responder offline não mantém indicador de carregamento como se o aplicativo estivesse tentando falar continuamente com o Studio.
- Swipe para eliminar alternativa agora usa destaque visual reforçado e rótulo explícito de alternativa eliminada.

## 0.12.0 — resultados offline e interface limpa

- Fast Refresh continua funcionando em desenvolvimento, mas o banner azul `Refreshing...` é suprimido pela interface do QuestFlow.
- O botão flutuante do Expo Dev Menu fica desabilitado nas novas builds nativas.
- Respostas feitas sem conexão ficam em **Questões → Questões respondidas offline** e recebem resultado, gabarito e explicação na próxima sincronização com o Studio.
- Preview/Production continuam sendo as builds recomendadas para uso diário, pois não exibem ferramentas de desenvolvimento.
