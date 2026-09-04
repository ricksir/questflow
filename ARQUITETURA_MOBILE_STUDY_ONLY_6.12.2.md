# Fronteira de produto — Mobile Study Only 6.12.2

## Regra de produto

O QuestFlow Mobile é um cliente de aprendizagem. Ele apresenta apenas conteúdo, ações e métricas necessárias para estudar.

O QuestFlow Studio é o console de operação e administração. Telegram, Saúde da IA, saúde do programa, serviços, arquitetura, Watchdog, Retrieval Health, Quality Gates, Cloud Bridge e diagnósticos permanecem no Studio.

## Telegram exclusivamente no Studio

A 6.12.2 remove a integração de controle do Telegram da superfície Mobile em três níveis:

1. **Interface:** Perfil e demais telas não exibem Telegram, estado do canal ou botões de pausa/retomada.
2. **Cliente/API:** `createApi()` e o contexto React não possuem operações de Telegram.
3. **Contrato do servidor:** `/api/v1/mobile/channels/telegram` não é exposto e `bootstrap`, `today` e `progress` não transportam o campo `channels`.

O histórico pedagógico continua consolidando respostas válidas independentemente da origem. A origem operacional não é mostrada no aplicativo, portanto uma resposta antiga registrada pelo Telegram ainda contribui para acurácia, domínio, memória e recomendações sem fazer o Mobile conhecer ou controlar o Telegram.

## Fronteira

```text
QuestFlow Studio
├── Telegram: configurar, pausar/retomar, diagnosticar, listener e filas
├── Saúde da IA / Retrieval Health / Quality Gates
├── Watchdog / serviços / arquitetura
└── aprendizagem e administração

QuestFlow Mobile
├── Hoje
├── Questões
├── Progresso
├── Revisões
├── Projeto de estudo
├── Lembretes
├── Salvamento offline
└── Conta do aparelho
```

## Regra para futuras funcionalidades

Um recurso só entra no Mobile se responder diretamente a uma necessidade de estudo: **o que estudar, responder, revisar, compreender ou acompanhar sobre a própria aprendizagem**. Controles de canais, infraestrutura e operação ficam no Studio.
