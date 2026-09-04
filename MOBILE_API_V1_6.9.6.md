# QuestFlow Mobile API v1 — Studio 6.9.6 / Mobile 0.3

O contrato funcional continua `questflow.mobile.v1` e o schema lógico continua versão 1. A 6.9.6 adiciona um **transporte**, não um segundo modelo de domínio.

## Transportes

### Studio local

`/api/v1/mobile/*` continua servido pelo Studio e é o caminho preferido quando acessível.

### Mobile Cloud Gateway

O Gateway expõe um subconjunto compatível para estudo fora da LAN:

- `GET /api/v1/mobile/health`
- `GET /api/v1/mobile/bootstrap`
- `GET /api/v1/mobile/today`
- `GET /api/v1/mobile/progress`
- `POST /api/v1/mobile/question-batches`
- `POST /api/v1/mobile/sync`
- `GET /api/v1/mobile/attempts/{attempt_id}/feedback`
- `DELETE /api/v1/mobile/devices/{device_id}`
- `GET /api/v1/mobile/cloud/status`

O Gateway não faz pareamento inicial. O QR é criado pelo Studio e pode transportar `cloud=<https-url>`.

## Rotas Studio ↔ Gateway

Protegidas por `X-QuestFlow-Bridge-Key` e destinadas somente ao Studio:

- `GET /bridge/v1/health`
- `POST /bridge/v1/publish`
- `POST /bridge/v1/drain`
- `POST /bridge/v1/ack`
- `GET /bridge/v1/status?tenant_id=...`

Protocolo: `questflow.mobile.cloud.v1`.

## Segurança e privacidade

O `publish` contém somente identidade técnica de tenant, hashes de sessões Mobile ativas, projeções específicas do aplicativo e um pacote limitado de estudo. O Gateway não recebe a credencial Turso nem uma cópia das tabelas internas do QuestFlow.

O payload público de cada questão continua sem gabarito. O material necessário para feedback fica separado no armazenamento do Gateway e só é devolvido após `answer_submitted` da própria sessão autenticada.

## Feedback provisório

Quando o Studio está offline, o Gateway pode responder com:

- `provisional: true`
- `source: cloud_bridge_study_pack`
- `timing.quality: pending_studio_validation`

Isso permite mostrar acerto/gabarito sem fingir que FSRS, KT, IRT e Quality Gate já foram recalculados. A autoridade final continua no Studio após `drain`.

## Cursores e idempotência

O Mobile mantém cursor por endpoint/transporte. `event_id` continua imutável e idempotente. Reenvio do mesmo ID/conteúdo é duplicata segura; reutilização com conteúdo diferente é rejeitada.
