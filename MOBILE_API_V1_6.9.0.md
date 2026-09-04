# QuestFlow Mobile API v1 — contrato da 6.9.0

Contrato: `questflow.mobile.v1`

A API é uma camada antiacoplamento. O aplicativo **não lê diretamente** `study_state`, `telegram_attempts`, `subject_analytics_daily`, FSRS, KT, IRT ou tabelas de curadoria.

## Pareamento e autenticação da fundação

1. No Studio: **Configurações → QuestFlow Mobile — Fundação 6.9.0 → Conectar novo aparelho**.
2. O Studio gera um token aleatório de uso único, validade de 5 minutos, e um QR `questflow://pair?...`.
3. O QR não contém URL/token administrativo do Turso.
4. O cliente troca o token por uma sessão Bearer de dispositivo.
5. Dispositivos podem ser revogados no Studio.

> Para produção multiusuário na internet, o adaptador de identidade cloud deverá usar OAuth/OIDC + PKCE. A 6.9.0 implementa o contrato e o pareamento seguro testável; não inventa um provedor de identidade externo sem infraestrutura/credenciais.

## Rotas

| Método | Rota | Função |
|---|---|---|
| POST | `/api/v1/mobile/pairing/exchange` | troca pareamento por sessão do aparelho |
| GET | `/api/v1/mobile/bootstrap` | identidade, projeto ativo, hoje, progresso e sync |
| GET | `/api/v1/mobile/today` | próxima ação/prioridades do dia |
| GET | `/api/v1/mobile/priorities` | prioridades por matéria |
| GET | `/api/v1/mobile/progress` | progresso agregado e timing confiável |
| POST | `/api/v1/mobile/question-batches` | lote priorizado de questões |
| GET | `/api/v1/mobile/questions/{uid}` | questão sem gabarito/explicação antes da resposta |
| POST | `/api/v1/mobile/events:batch` | eventos imutáveis/idempotentes |
| GET | `/api/v1/mobile/attempts/{id}/feedback` | gabarito/explicação depois da tentativa |
| GET | `/api/v1/mobile/sync?cursor=N` | pull incremental por cursor |
| POST | `/api/v1/mobile/sync` | push de outbox + pull incremental |
| POST | `/api/v1/mobile/devices/push-token` | registra token FCM/APNs bridge |
| DELETE | `/api/v1/mobile/devices/{device_id}` | aparelho revoga a própria sessão |

## Evento universal

```json
{
  "event_id": "UUID",
  "schema_version": 1,
  "event_type": "answer_submitted",
  "device_id": "device UUID",
  "session_id": "session UUID",
  "attempt_id": "attempt UUID",
  "exam_project_id": "project UUID",
  "question_id": "question UID",
  "question_revision": 3,
  "occurred_at": "2026-08-17T12:00:00-03:00",
  "sequence_no": 18,
  "client": {"platform": "ios", "version": "0.1.0"},
  "payload": {
    "selected_index": 1,
    "confidence": "high",
    "perceived_difficulty": "hard",
    "active_response_seconds": 42.0,
    "wall_response_seconds": 3600.0,
    "idle_seconds": 3558.0,
    "max_idle_gap_seconds": 3500.0,
    "interaction_count": 4,
    "timing_source": "client_active_timer_v1"
  }
}
```

`event_id` é único. Reenvio do mesmo evento devolve ACK/duplicidade e **não reaplica** tentativa, FSRS, KT ou IRT.

## Vocabulário inicial de eventos

`session_started`, `session_ended`, `question_presented`, `question_opened`, `answer_selected`, `answer_changed`, `answer_submitted`, `confidence_reported`, `difficulty_reported`, `result_seen`, `explanation_opened`, `explanation_finished`, `learning_gap_reported`, `question_skipped`, `hint_requested`, `scaffold_used`.

## Revisões de questão

Cada conteúdo servido recebe `question_revision`. O snapshot da revisão apresentada é imutável. Se o Studio corrigir o gabarito enquanto o celular está offline, a tentativa antiga é avaliada contra a revisão que o usuário realmente viu.

## Offline-first

O futuro cliente deverá gravar localmente antes de depender da rede:

```text
UI → SQLite local → outbox → POST /events:batch ou /sync → ACK por event_id → cursor de pull
```

Sincronização em background é otimização. A garantia é a fila persistente + idempotência.

## Tempo de resposta

`response_seconds` passa a significar **tempo ativo aprovado**, não tempo total de relógio. Consulte `MOBILE_DATA_CATALOG.md` para a política completa.
