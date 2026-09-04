# Validação QuestFlow Studio 6.9.3

Escopo: clareza dos Quality Gates, Visão Geral orientada à ação, Painel Visual explicável e pausa persistente de questões do Telegram.

## Resultados
- 59/59 testes direcionados aprovados.
- `node --check web/app.js`: aprovado.
- `python -m compileall`: aprovado.
- Teste de tempo: 3600 s de relógio / 42 s ativos resulta em média ativa de 42 s.
- Respostas Mobile aparecem no resumo de atividade por canal.
- Pausa de questões Telegram bloqueia `send_cycle` antes de qualquer envio.
- Quality Gate com amostra insuficiente deixa de exibir Score/Recall/Grounding como "OK" na UI.

## Comportamento da pausa Telegram
A configuração `telegram_questions_paused` é persistida. O listener permanece conectado para processar respostas e comandos; ficam bloqueados novos ciclos, reenvios de questões sem resposta, retries de deliveries e relearning automático enquanto a pausa estiver ativa.
