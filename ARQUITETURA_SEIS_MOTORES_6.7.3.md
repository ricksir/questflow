# Arquitetura dos seis motores — QuestFlow 6.7.3

A versão **6.7.3** mantém exatamente os seis motores existentes. Production Hardening é uma camada transversal de empacotamento, instalação, recuperação e verificação; não é um novo motor pedagógico.

1. **Banco Editorial** — questões, proveniência, Curadoria e persistência editorial.
2. **Learner Model** — FSRS, Knowledge Tracing, IRT, incerteza e calibração.
3. **Learning Engine** — recomendação, simulados, coleta de evidência e benchmark pedagógico.
4. **Knowledge Engine** — RAG híbrido, grafo e contexto local.
5. **AI Engine** — Tutor, scaffolding, geração assistida e pesquisa Google editorial.
6. **Evaluation & Governance Engine** — auditoria, avaliação por afirmação/evidência e revisão humana.

## Camada transversal 6.7.3

Release source → lock exato + SHA-256 → SBOM → auditoria → matriz 3.11–3.14 → CI local → pacote.

Atualização → validação de hash → staging seguro → backup SQLite consistente → smoke test → aplicação → `PRAGMA quick_check` → teste de restauração → sucesso.

Qualquer falha crítica após a aplicação aciona rollback do código; o banco local continua sendo a autoridade e só é restaurado a partir do backup se o próprio `quick_check` indicar dano.
