# Arquitetura de seis motores — 6.6.3

A arquitetura permanece com exatamente seis motores:
1. Banco Editorial — qf-editorial-engine-3
2. Learner Model — qf-learner-engine-2
3. Learning Engine — qf-learning-engine-4
4. Knowledge Engine — qf-knowledge-engine-2
5. AI Engine — qf-ai-engine-3
6. Evaluation & Governance Engine — qf-ai-governance-4

## Mudança da 6.6.3
A correção pertence ao **Banco Editorial** e à infraestrutura transversal de sincronização.

A Curadoria diferencia agora:
- conteúdo editorial durável: enunciado, classificação, comentário, proveniência, revisão;
- sinais derivados: qualidade, status calculado, origem normalizada do comentário e dificuldade empírica.

Sinais derivados podem ser reconstruídos localmente e, isoladamente, não geram eventos de Cloud Sync. Essa separação impede que uma leitura/recalculo seja confundida com edição de conteúdo.
