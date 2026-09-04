# Arquitetura dos seis motores — QuestFlow Studio 6.7.0

A versão 6.7.0 mantém **exatamente seis motores**. Scaffolding e revisão multimodal foram incorporados às fronteiras existentes, sem criar um “Tutor Engine” adicional.

## 1. Banco Editorial — `qf-editorial-engine-3`
Questões, proveniência, Curadoria, Projeto/Edital, legislação temporal e estados editoriais.

## 2. Learner Model — `qf-learner-engine-3`
FSRS/estado de aprendizagem, Knowledge Tracing, IRT, calibração/incerteza e agora o **sinal de suporte do scaffolding**. Mantém indicadores de sessões, independência e necessidade de ajuda.

## 3. Learning Engine — `qf-learning-engine-5`
Fila de estudo, precedência FSRS, recomendador multiobjetivo, simulados adaptativos e persistência operacional das sessões de scaffolding.

## 4. Knowledge Engine — `qf-knowledge-engine-2`
RAG híbrido, grafo de conhecimento, chunks, evidências e contexto relacionado à questão.

## 5. AI Engine — `qf-ai-engine-4`
Tutor, AI Gateway, comentários, geração controlada e **scaffolding progressivo**. Possui seis níveis e representações texto/flashcard/passo a passo/visual. Imagens binárias permanecem locais na 6.7.0.

## 6. Evaluation & Governance — `qf-ai-governance-4`
Avaliação por afirmação/evidência, Questões Ouro, auditoria, telemetria, aprovação humana e registro auditável das pistas do Tutor.

## Infraestrutura transversal preservada

- Runtime Watchdog & Self-Healing;
- event loop assíncrono para I/O;
- rate limiting;
- Cloud Sync/Turso offline-first;
- Centro de Privacidade da IA;
- Structured Outputs e defesa contra prompt injection;
- versionamento e compatibilidade do runtime.

## Fluxo do Socrático Progressivo

`Questão → contexto do aluno → nível 0 → pista 1 → pista 2 → ... → nível resolvido → sinal de suporte → Learner Model`

Se o aluno solicitar explicação completa:

`nível 5 → Tutor completo → RAG → Evaluation & Governance → auditoria`.

O nível de suporte é um **sinal complementar**. Ele não substitui FSRS, KT ou IRT.
