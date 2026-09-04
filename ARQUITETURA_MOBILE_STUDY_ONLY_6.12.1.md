# Fronteira de produto — Mobile Study Only 6.12.1

## Regra

O QuestFlow Mobile é um cliente de aprendizagem. Ele apresenta apenas informações e ações necessárias para estudar. Saúde da IA, saúde do runtime, serviços, arquitetura, Quality Gates, Watchdog, diagnóstico de rede e detalhes operacionais permanecem no QuestFlow Studio.

## Mobile

Exposto ao usuário:
- Hoje / plano de estudo;
- Questões e feedback;
- Progresso e métricas pedagógicas;
- projeto ativo;
- revisões e questões sugeridas;
- lembretes de estudo;
- salvamento do progresso;
- preferência de entrega de questões pelo Telegram;
- ação mínima de desconectar a conta do aparelho.

Não exposto ao usuário:
- Saúde da IA / Retrieval Health;
- Score técnico, Recall técnico, Grounding e Quality Gates;
- Watchdog e saúde do programa;
- serviços, workers e filas técnicas;
- endpoints, rotas, cursor de sincronização e nomes de transportes;
- Cloud Bridge como conceito de arquitetura;
- versão/contrato como diagnóstico de tela;
- promover release, override e rollback.

## Contrato e segurança

- `GET /api/v1/mobile/ai-health` foi removido.
- `AiHealthProjection` e `createApi().aiHealth()` foram removidos do cliente Expo.
- a tela `mobile/app/ai-health.tsx` e sua rota foram removidas.
- o Cloud Bridge publica somente `bootstrap`, `today` e `progress`.
- o Cloud Gateway descarta/purga a projeção legada `ai_health` quando recebe uma nova publicação do tenant.
- o endpoint público `/api/v1/mobile/health` continua existindo apenas como mecanismo interno de descoberta/conectividade e não é apresentado como conteúdo de produto.

## Studio

Permanecem no programa:
- RetrievalHealthService;
- Observabilidade de Retrieval;
- Quality Gates;
- Evaluator Worker;
- Watchdog / Runtime Supervisor;
- Cloud Sync / Mobile Cloud Bridge e diagnósticos;
- arquitetura dos seis motores e serviços transversais.

## Fluxo

```text
QuestFlow Studio
├── Aprendizagem / seis motores
├── Retrieval Health / Quality Gates
├── Watchdog / serviços / diagnóstico
└── Mobile Foundation
      ├── Today ───────────────► Mobile
      ├── Questions ───────────► Mobile
      ├── Progress ────────────► Mobile
      └── Sync operacional ────► Mobile (interno, não exibido como arquitetura)

Saúde/arquitetura/serviços ────X──► Mobile
```

## Impacto pedagógico

A separação evita que métricas técnicas de IA sejam confundidas com desempenho do aluno. A prática de recuperação, repetição espaçada/FSRS, prioridade de revisão, acurácia e memória continuam pertencendo aos contratos pedagógicos `Today`/`Progress` e ao fluxo de Questões.
