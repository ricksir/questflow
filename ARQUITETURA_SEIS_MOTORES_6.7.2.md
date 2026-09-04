# Arquitetura dos seis motores — QuestFlow 6.7.2

A versão 6.7.2 mantém exatamente seis motores.

1. **Banco Editorial** — questões, proveniência, Curadoria e persistência editorial.
2. **Learner Model** — FSRS, Knowledge Tracing, IRT, incerteza e calibração.
3. **Learning Engine** — recomendação, simulados, coleta de evidência e benchmark pedagógico.
4. **Knowledge Engine** — RAG híbrido, grafo e contexto local.
5. **AI Engine** — Tutor, scaffolding, geração assistida e agora a pesquisa Google de comentário editorial.
6. **Evaluation & Governance Engine** — auditoria, avaliação por afirmação/evidência e revisão humana.

## Fluxo novo da 6.7.2

Editor da questão
→ política de privacidade
→ Google Modo IA (código da questão; fallback pelo enunciado)
→ extração da explicação/gabarito sugerido
→ AI Engine
→ Evaluation & Governance
→ rascunho no campo “Explicação após a resposta”
→ origem “IA assistida + revisão humana”
→ revisão e salvamento explícitos pelo usuário.

O Google nunca recebe autoridade para sobrescrever o gabarito persistido da questão.
