# QuestFlow Mobile — Catálogo de Dados 6.10.0 / Mobile 0.7 Alpha

Este catálogo define o conjunto mínimo de dados que a fundação mobile pode coletar/sincronizar. A regra é **necessidade pedagógica**: o aplicativo não deve coletar dados sem relação direta com estudo, segurança da conta ou sincronização.

| Dado | Coletado | Finalidade | Retenção | Sincroniza | Observação |
|---|---:|---|---|---:|---|
| `account_id` / `tenant_id` / `learner_id` | Sim | isolamento de usuário | enquanto existir a conta | Sim | resolvido pelo servidor; cliente não escolhe tenant arbitrário |
| `device_id` | Sim | sessão, revogação, sync | até revogação/conta | Sim | identificador QuestFlow, não advertising ID |
| `exam_project_id` | Quando aplicável | separar concurso/prova | histórico | Sim | nunca mistura pessoas diferentes |
| configuração da sessão | Sim | retomar lote e registrar objetivo do estudo | até encerrar/descartar a sessão | Local + evento de sessão | modo, quantidade e matéria; não contém gabarito |
| ponto de retomada da sessão | Sim | continuar após fechar o app | até encerrar/descartar a sessão | Local | índice, etapa e tentativa atual ficam no SQLite do aparelho |
| questão/revisão apresentada | Sim | preservar o conteúdo realmente visto | histórico | Sim | `question_revision` + snapshot |
| resposta final | Sim | aprendizagem/correção | histórico | Sim | evento idempotente |
| primeira seleção/mudança | Opcional no cliente | hesitação/metacognição | histórico de eventos | Sim | sem coordenadas de toque |
| confiança | Sim quando informada | calibração metacognitiva | histórico | Sim | coletada antes do gabarito |
| dificuldade percebida | Sim quando informada | metacognição | histórico | Sim | fácil/média/difícil |
| lacuna “preciso estudar” | Sim quando informada | prioridade/recomendação | histórico | Sim | sinal explícito do usuário |
| solicitação de correção antes da resposta | Quando acionada | curadoria da questão | até resolução | Sim | não cria tentativa; origem `mobile_preanswer` |
| assunto ainda não estudado | Quando acionado | separar conteúdo não estudado das métricas | até o usuário marcar como estudado | Sim | backlog por matéria/assunto/aula; não conta como erro |
| tempo ativo da resposta | Sim | tendência de fluidez | histórico | Sim | somente se Quality Gate aprovar |
| tempo total de relógio | Sim | auditoria de qualidade do timing | histórico | Sim | **não** é usado como “velocidade” por si só |
| tempo ocioso agregado | Sim | remover tela abandonada da velocidade | histórico/evento | Sim | sem registrar cada toque |
| maior intervalo ocioso agregado | Sim no cliente oficial | detectar questão deixada aberta | evento | Sim | apenas duração agregada |
| contagem agregada de interações | Sim no cliente oficial | qualidade da temporização | evento | Sim | não guarda coordenadas/conteúdo de toques |
| push token | Quando push ativado | notificações | até revogação/troca | Sim | armazenado por dispositivo |
| localização | **Não** | — | — | Não | fora do escopo |
| contatos | **Não** | — | — | Não | fora do escopo |
| microfone | **Não** no núcleo | — | — | Não | fora do escopo |
| advertising ID | **Não** | — | — | Não | fora do escopo |

## Quality Gate do tempo de resposta

O QuestFlow **não calcula velocidade por `respondeu_em - abriu_em`**. Esse cálculo confunde estudo com abandono da tela.

O cliente oficial deverá enviar agregados:

```json
{
  "active_response_seconds": 42.0,
  "wall_response_seconds": 3600.0,
  "idle_seconds": 3558.0,
  "max_idle_gap_seconds": 3500.0,
  "interaction_count": 4,
  "timing_source": "client_active_timer_v1"
}
```

Regras preservadas na 6.10.0 / Mobile 0.7:

- background, tela bloqueada e perda de foco da questão pausam a medição ativa;
- o cliente oficial deixa de acumular tempo ativo após 60 s sem interação e retoma somente quando há nova interação;
- inatividade prolongada é classificada localmente e informada apenas como agregados;
- uma questão aberta por horas pode ter poucos segundos/minutos de tempo ativo válido;
- wall-clock sem medição ativa confiável é mantido para auditoria, mas excluído das médias;
- atividade acima de 30 minutos é tratada como outlier de timing (a resposta continua válida);
- longa abertura quase sem interação e sem separação coerente de ociosidade é `idle_contaminated`;
- `idle_contaminated`, `abandoned`, `outlier`, `wall_clock_unverified` e `legacy_unverified` ficam fora de métricas/modelos de velocidade;
- acerto/erro, FSRS/KT/IRT e histórico da tentativa permanecem preservados; somente o sinal de **velocidade** é descartado quando duvidoso.

O limite de inatividade é um **guardrail de qualidade**, não um limite pedagógico de quanto tempo alguém “pode” pensar numa questão. Em caso de dúvida, a política é conservadora: descartar a amostra de velocidade em vez de penalizar o usuário.
