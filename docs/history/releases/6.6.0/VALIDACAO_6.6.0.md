# Validação técnica — QuestFlow Studio 6.6.0

## Escopo

A 6.6.0 evolui o Learner Model sem alterar a arquitetura de seis motores. O foco é reduzir falsa precisão: estimativas com pouca evidência passam a ser explicitamente abstidas; previsões pré-resposta são persistidas para calibração; e o sistema produz planos contrafactuais conservadores.

## Migração

- `question_bank`: permanece em v8.
- `study`: v9 → **v10**.
- `ai_governance`: permanece em v3.

A migração v10 adiciona às tentativas:

- `learner_predicted_probability`;
- `learner_prediction_confidence`;
- `learner_prediction_low` / `learner_prediction_high`;
- `learner_prediction_status`;
- `learner_prediction_reason`;
- `learner_prediction_version`.

## Upgrade real 6.5.2 → 6.6.0

Foi criada uma base com o código original da 6.5.2 contendo uma questão, 8 tentativas e 8 eventos do Learner Model. A mesma base foi depois aberta pela 6.6.0.

Resultado:

- versões `study`: `[1..9]` → `[1..10]`;
- tentativas preservadas: **8/8**;
- eventos Learner Model preservados/reconstruídos: **8/8**;
- previsões históricas pré-resposta criadas: **8/8**;
- decisões históricas: 4 `evidencia_insuficiente` + 4 `estimativa_cautelosa` no cenário de teste;
- `PRAGMA quick_check = ok`;
- `PRAGMA foreign_key_check`: **0 violações**;
- Learner Model final: `qf-learner-2`.

O backfill é cronológico e não altera os cartões FSRS nem o histórico bruto de respostas.

## Testes automatizados

A suíte integral contém **330 testes**. A execução única excedeu o timeout do ambiente sem falhas registradas; a mesma suíte foi então particionada em três grupos:

- grupo A: **119/119**;
- grupo B: **112/112**;
- grupo C: **99/99**.

Total: **330/330 aprovados**.

Também foram executados testes específicos da 6.6.0 para:

- abstenção por baixa evidência;
- transição para estimativa cautelosa/confiável;
- intervalo probabilístico;
- Brier Score e ECE seletivos;
- cobertura/taxa de abstenção;
- plano contrafactual BKT;
- preservação dos seis motores;
- allowlist HTTP do novo endpoint;
- Tutor IA respeitando a abstenção.

## API HTTP real

Pela mesma rota `/api/call` usada pela interface foram validados:

- `get_learning_model` → HTTP 200;
- `get_counterfactual_learning_plan` → HTTP 200.

## Integridade metodológica

- FSRS continua responsável pelo momento da revisão.
- KT continua estimando domínio conceitual.
- IRT continua pessoal e fortemente regularizada.
- baixa confiança não é transformada em “domínio baixo/alto”: o sistema pode se abster.
- plano contrafactual é uma simulação do BKT e não uma garantia causal de aprendizagem.
