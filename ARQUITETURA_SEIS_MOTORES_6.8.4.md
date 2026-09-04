# Arquitetura dos seis motores — QuestFlow 6.8.4

A versão 6.8.4 mantém **exatamente seis motores**.

1. Banco Editorial
2. Learner Model
3. Learning Engine
4. Knowledge Engine **3.4**
5. AI Engine
6. Evaluation & Governance Engine

## Fluxo de Quality Gate

Questões Ouro → Benchmark Multimodal → snapshot atual → baseline aprovada → thresholds versionados → Quality Gates → APTO ou QUARENTENA → decisão humana → PROMOÇÃO / OVERRIDE auditado → nova baseline aprovada.

Rollback de Quality Gate restaura a baseline e o perfil de reranking aprovados anteriormente. O mecanismo não substitui o rollback binário do atualizador seguro.

FSRS continua soberano para revisão, KT para domínio e IRT para habilidade/informação.
