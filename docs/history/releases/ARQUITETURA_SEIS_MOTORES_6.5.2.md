# Arquitetura dos seis motores — QuestFlow Studio 6.5.2

A 6.5.2 é uma correção de infraestrutura e **não altera as fronteiras dos seis motores** definidas na 6.5.1.

1. **Banco Editorial** — questões, curadoria, edital, legislação temporal e proveniência.
2. **Learner Model** — FSRS, Knowledge Tracing e IRT.
3. **Learning Engine** — prioridades, Central Hoje e simulados adaptativos.
4. **Knowledge Engine** — RAG híbrido, grafo e conhecimento recuperável.
5. **AI Engine** — AI Gateway, Tutor, comentários e geração controlada.
6. **Evaluation & Governance Engine** — avaliação independente, privacidade, telemetria, auditoria e Questões Ouro.

## Infraestrutura Cloud Sync

O Cloud Sync permanece transversal e local-first. Ele não é um sétimo motor. A 6.5.2 adiciona:

- diagnóstico detalhado da outbox;
- dead-letter local para eventos legados estruturalmente não transmissíveis;
- sincronização bounded-until-idle;
- visibilidade de tentativas/erros;
- distinção entre igualdade de contagem de questões e sincronização completa dos eventos.
