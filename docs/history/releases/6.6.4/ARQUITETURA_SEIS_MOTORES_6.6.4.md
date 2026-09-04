# Arquitetura dos seis motores — 6.6.4

A 6.6.4 preserva o monólito modular com exatamente seis motores:

1. **Banco Editorial** — questões, proveniência, qualidade e Curadoria.
2. **Learner Model** — FSRS, Knowledge Tracing, IRT, incerteza e calibração.
3. **Learning Engine** — recomendação, Central Hoje e simulados adaptativos.
4. **Knowledge Engine** — RAG híbrido, índice semântico e grafo de conhecimento.
5. **AI Engine** — Tutor, geração controlada e AI Gateway multiprovedor.
6. **Evaluation & Governance Engine** — avaliação por afirmação/evidência, auditoria e Questões Ouro.

## Alteração arquitetural desta release

A mudança está exclusivamente na fronteira do **Banco Editorial** e na infraestrutura de persistência derivada:

- qualidade editorial e decisão humana passam a ser sinais distintos;
- a decisão humana explícita pode concluir uma questão B quando não existem bloqueadores críticos;
- dados derivados/reconstruíveis não são tratados como alterações de domínio pelo Cloud Sync.

Não foi criado um sétimo motor.
