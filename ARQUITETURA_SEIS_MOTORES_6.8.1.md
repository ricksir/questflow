# Arquitetura dos seis motores — QuestFlow 6.8.1

A versão 6.8.1 mantém exatamente seis motores.

1. **Banco Editorial** — questões, proveniência, Curadoria e persistência editorial.
2. **Learner Model** — FSRS, Knowledge Tracing, IRT, incerteza e calibração.
3. **Learning Engine** — recomendação, simulados e coleta de evidência.
4. **Knowledge Engine 3.1** — RAG textual/visual/híbrido e grounding multimodal auditável.
5. **AI Engine** — Tutor, scaffolding, geração assistida, pesquisa Google editorial e orquestração do benchmark.
6. **Evaluation & Governance Engine** — Questões Ouro, auditoria, avaliação por afirmação/evidência e revisão humana.

## Novo fluxo 6.8.1

Questões Ouro
→ recuperação Textual / Visual / Híbrida
→ comparação contra snapshots ouro
→ precisão/recall + grounding + suporte + cobertura visual
→ ganho híbrido
→ painel Benchmark RAG 3.0
→ decisão humana sobre ajustes futuros de reranking.

O benchmark não altera automaticamente pesos de retrieval nesta versão.
