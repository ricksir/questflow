# QuestFlow Mobile API v1 — Studio 6.9.1 / Mobile 0.1 Alpha

A 6.9.1 preserva o contrato `questflow.mobile.v1` criado na 6.9.0 e acrescenta o primeiro cliente móvel funcional. O aplicativo consome projeções próprias; ele **não acessa diretamente** `study_state`, tentativas, FSRS, KT, IRT ou outras tabelas internas do Studio.

## Pareamento Alpha na rede local

1. No Studio, habilite o acesso móvel pela rede local e reinicie o servidor quando solicitado.
2. Abra **Configurações → QuestFlow Mobile 0.1 — Alpha integrado ao Studio 6.9.1**.
3. Clique em **Conectar novo aparelho**.
4. O QR contém apenas:
   - contrato `api=v1`;
   - token de pareamento de uso único e curta validade;
   - endereço local do Mobile API, como `http://192.168.1.20:53155`.
5. O QR **não contém** URL administrativa do Turso, token de banco, senha ou chave de provisionamento.
6. O app troca o token de pareamento por sua sessão e grava o segredo da sessão no SecureStore do aparelho.

Nesta fase Alpha, Studio e celular precisam alcançar a mesma API local. A implantação internet/cloud com OAuth/OIDC + PKCE continua sendo etapa posterior; a release não simula infraestrutura externa inexistente.

## Endpoints

| Método | Endpoint | Autenticação | Função |
|---|---|---|---|
| GET | `/api/v1/mobile/health` | Não | Descoberta/saúde mínima da API para pareamento |
| POST | `/api/v1/mobile/pairing/exchange` | Token de pareamento | Troca token temporário por sessão do aparelho |
| GET | `/api/v1/mobile/bootstrap` | Bearer | Identidade/projeto/sync/dispositivos |
| GET | `/api/v1/mobile/today` | Bearer | Projeção da tela Hoje |
| GET | `/api/v1/mobile/priorities` | Bearer | Prioridades por matéria |
| GET | `/api/v1/mobile/progress` | Bearer | Progresso simplificado |
| POST | `/api/v1/mobile/question-batches` | Bearer | Lote priorizado sem gabarito |
| GET | `/api/v1/mobile/questions/{question_id}` | Bearer | Questão/revisão específica |
| POST | `/api/v1/mobile/events:batch` | Bearer | Eventos idempotentes |
| GET | `/api/v1/mobile/attempts/{attempt_id}/feedback` | Bearer | Gabarito/explicação **depois** da tentativa processada |
| GET/POST | `/api/v1/mobile/sync` | Bearer | Pull por cursor e push de outbox |
| POST | `/api/v1/mobile/devices/push-token` | Bearer | Registra token nativo APNs/FCM |
| DELETE | `/api/v1/mobile/devices/{device_id}` | Bearer | Revoga o próprio aparelho |

## Offline-first no Mobile 0.1

O cliente possui SQLite local com:

- `qf_question_cache` — questões/revisões já recebidas **sem gabarito**;
- `qf_outbox` — eventos ainda sem ACK;
- `qf_local_attempts` — tentativa local e feedback posterior;
- `qf_meta` — cursor e metadados mínimos de sincronização.

Fluxo:

```text
UI → SQLite local → outbox persistente → /sync → ACK por event_id → feedback/projeções
```

Perda de internet não apaga a resposta. Reenvio do mesmo `event_id` não reaplica o efeito. Se um evento imutável foi persistido mas seu processamento falhou no servidor, a 6.9.1 permite reprocessar **o mesmo conteúdo**; reutilizar o mesmo `event_id` com conteúdo alterado é rejeitado.

## Gabarito e metacognição

O lote de questões não leva gabarito ao cache. O fluxo do cliente é:

```text
questão → alternativa → confiança → dificuldade opcional → enviar → sincronizar → feedback
```

A confiança é coletada antes de revelar o resultado. Se a tentativa foi feita offline, o app confirma que a resposta está salva, mas não inventa correção local: gabarito e explicação aparecem somente depois do processamento pelo Studio contra a `question_revision` realmente apresentada.

## Tempo de resposta confiável

O Mobile 0.1 implementa `client_active_timer_v1` e envia separadamente:

```json
{
  "active_response_seconds": 42.0,
  "wall_response_seconds": 3600.0,
  "idle_seconds": 3558.0,
  "max_idle_gap_seconds": 3600.0,
  "interaction_count": 1,
  "timing_source": "client_active_timer_v1"
}
```

Regras do cliente:

- background/inatividade do app não acumulam tempo ativo;
- a tela pode permanecer aberta por horas sem transformar horas em “tempo de resposta”;
- após 60 segundos sem interação, o cronômetro deixa de acumular até a próxima interação;
- o Studio ainda aplica seu Quality Gate e pode excluir amostras duvidosas das métricas de velocidade;
- excluir o tempo da métrica **não invalida a resposta** para acerto/erro e aprendizagem.

O limite de 60 segundos é guardrail técnico para estimar atividade, não limite de quanto tempo o usuário pode pensar.

## Privacidade do cliente Alpha

O núcleo não coleta localização, contatos, microfone nem advertising ID. A câmera é solicitada somente quando o usuário abre o leitor de QR. Push é opt-in por aparelho e transporta sinal de notificação/sincronização, não o conteúdo integral da questão.
