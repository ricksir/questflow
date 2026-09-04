# Arquitetura — Saúde da IA no Mobile 6.12.0

## Objetivo

Expor ao QuestFlow Mobile o estado técnico de Retrieval/Knowledge Base sem misturar essas informações com as métricas pedagógicas do learner.

## Fronteira de contrato

Novo contrato read-only:

- `questflow.mobile.ai_health.v1`
- `GET /api/v1/mobile/ai-health`
- autenticação: Bearer já emitido no pareamento
- comandos administrativos expostos: nenhum

A projeção contém somente:

- estado do `RetrievalHealthService`;
- última avaliação técnica persistida;
- Score/Recall/Grounding técnicos somente quando avaliáveis;
- cobertura/chunks/fontes do último snapshot;
- drift do índice;
- estado resumido do Quality Gate;
- transporte (`studio_lan` ou `cloud_bridge`).

Ela não contém acurácia do aluno, mastery, FSRS, retrievability de memória, revisões devidas, prioridade de estudo, histórico de respostas ou `learner_id`.

## Fluxo Studio local

```text
RetrievalHealthService
  -> Metrics Snapshot Store (read-only)
  -> mobile_projection()
  -> MobileFoundationService.ai_health_projection()
  -> GET /api/v1/mobile/ai-health
  -> QuestFlow Mobile 0.8.0 / Saúde da IA
```

Abrir a tela no celular não executa benchmark, não recalcula o índice e não grava estado.

## Fluxo Cloud Bridge

```text
RetrievalHealthService
  -> projeção mobile-safe
  -> MobileCloudBridgeEngine.publish()
  -> projection kind=ai_health
  -> Mobile Cloud Gateway
  -> GET /api/v1/mobile/ai-health
  -> Mobile
```

No gateway a projeção permanece somente leitura e recebe `delivery.transport=cloud_bridge` e `last_studio_publish_at`.

## Isolamento pedagógico

A tela Saúde da IA fica em `Perfil > Sistema > Saúde da IA`, fora das telas Hoje, Questões e Progresso. O próprio contrato declara:

```json
{
  "separation": {
    "pedagogical_metrics": false,
    "learner_data": false,
    "affects_study_score": false
  }
}
```

Isso impede que Score/Recall/Grounding de retrieval sejam confundidos com acerto, domínio ou memória do aluno.

## Semântica de ausência de amostra

Quando não existe amostra Ouro suficiente:

- Score = `null`
- Recall = `null`
- Grounding = `null`
- UI = `Não avaliado`

Nunca é convertido para `0.0`.

## Operações administrativas

O Mobile não recebe endpoints para:

- reavaliar retrieval;
- promover release;
- override;
- rollback;
- alterar baseline.

Essas operações continuam exclusivas do Studio.

## Compatibilidade

- Studio: 6.12.0
- Mobile: 0.8.0
- protocolo base Mobile: `questflow.mobile.v1` preservado
- Cloud Bridge: `questflow.mobile.cloud.v1` preservado; nova projeção é aditiva
- dependências React Native/Expo: inalteradas
- migração SQLite: não necessária
