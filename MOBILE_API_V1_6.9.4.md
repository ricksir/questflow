# QuestFlow Mobile API v1 — Studio 6.9.4 / Mobile 0.2

Contrato preservado: `questflow.mobile.v1`.

A 6.9.4 é aditiva. O cliente continua sem acesso direto a `study_state`, FSRS, KT, IRT ou outras tabelas internas.

## Novidades de projeção

### `/api/v1/mobile/today`
Além dos campos anteriores, retorna:

- `coach.headline`;
- `coach.what_happened`;
- `coach.why_it_matters`;
- `coach.next_action`;
- `channels`;
- `recent_activity`.

### `/api/v1/mobile/progress`
Além dos campos anteriores, retorna:

- `summary.correct` / `summary.wrong`;
- `summary.timing_samples`;
- `summary.today_attempts`;
- `summary.channels.mobile|telegram|desktop`;
- `summary.coach_text`;
- `recent_activity`;
- `subjects[].insight` com desempenho recente, tendência, lacuna declarada, dificuldade e assuntos fracos.

## Controle de canal Telegram

| Método | Rota | Autenticação | Função |
|---|---|---|---|
| GET | `/api/v1/mobile/channels/telegram` | Bearer | Consultar estado do canal |
| PUT/POST | `/api/v1/mobile/channels/telegram` | Bearer | Pausar/retomar novas questões |

Exemplo de corpo:

```json
{
  "questions_paused": true
}
```

Esse controle não desliga o listener. Ele bloqueia somente novos envios/reenvios de questões enquanto preserva respostas, comandos e histórico.

## Compatibilidade

O schema lógico permanece versão 1 e o contrato permanece `questflow.mobile.v1`. Clientes 0.1.x podem ignorar os campos adicionais.
