# QuestFlow Studio 6.5.1 — Arquitetura dos seis motores

A 6.5.1 **não cria um sétimo motor**. O AI Gateway é uma camada interna do AI Engine, e a observabilidade pertence ao Evaluation & Governance Engine.

1. **Banco Editorial — `qf-editorial-engine-3`**
   - questões, proveniência, edital, legislação temporal, curadoria e atualidade.
2. **Learner Model — `qf-learner-engine-1`**
   - FSRS, Knowledge Tracing e IRT pessoal.
3. **Learning Engine — `qf-learning-engine-3`**
   - Central Hoje, recomendação multiobjetivo e simulados adaptativos.
4. **Knowledge Engine — `qf-knowledge-engine-2`**
   - RAG híbrido, grafo e evidências. Na fronteira com IA, evidências passam a ser `untrusted_data`.
5. **AI Engine — `qf-ai-engine-3`**
   - Tutor, comentários, geração controlada e **AI Gateway**: privacidade → sanitização → Structured Output → provedor → validação.
6. **Evaluation & Governance Engine — `qf-ai-governance-3`**
   - avaliação independente, decisões humanas, auditoria, Questões Ouro e telemetria de provedores.

Princípios adicionais da 6.5.1: `structured_outputs`, `prompt_injection_defense`, `privacy_minimization` e `ai_observability`.
