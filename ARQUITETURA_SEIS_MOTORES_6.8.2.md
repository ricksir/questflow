# Arquitetura dos seis motores — QuestFlow 6.8.2

A versão 6.8.2 mantém exatamente seis motores.

1. **Banco Editorial** — questões, proveniência e Curadoria.
2. **Learner Model** — FSRS, KT, IRT, incerteza e calibração pedagógica.
3. **Learning Engine** — recomendação, simulado e coleta de evidência.
4. **Knowledge Engine 3.2** — RAG textual/visual/híbrido, reranking calibrado, baseline e regressão de retrieval.
5. **AI Engine** — Tutor, scaffolding, geração e assistência editorial.
6. **Evaluation & Governance** — Questões Ouro, auditoria, benchmark e revisão humana.

## Fluxo novo

Questões Ouro → recuperação textual/visual → perfis candidatos explícitos → A/B offline → recomendação → confirmação humana → perfil versionado → retrieval híbrido → benchmark → comparação com baseline → alerta de regressão/rollback.

A calibração de retrieval não modifica FSRS, KT ou IRT e não substitui a revisão humana.
