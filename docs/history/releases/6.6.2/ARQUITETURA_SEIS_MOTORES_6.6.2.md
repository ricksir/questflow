# Arquitetura dos seis motores — 6.6.2

A correção 6.6.2 não cria um novo motor e não altera as fronteiras arquiteturais:

1. Banco Editorial — `qf-editorial-engine-3`
2. Learner Model — `qf-learner-engine-2`
3. Learning Engine — `qf-learning-engine-4`
4. Knowledge Engine — `qf-knowledge-engine-2`
5. AI Engine — `qf-ai-engine-3`
6. Evaluation & Governance Engine — `qf-ai-governance-4`

O Cloud Sync continua sendo infraestrutura transversal local-first. A mudança desta
release reforça uma regra arquitetural: **consulta/pré-visualização não é comando**.
O Learning Engine pode calcular scores, retrievability e recomendações para exibição
sem materializá-los no estado durável. Quando uma seleção operacional precisar manter
métricas derivadas localmente, o gatilho do Cloud Sync distingue esses campos de uma
mudança real do estado de aprendizagem.
