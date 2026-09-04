# Arquitetura dos seis motores — QuestFlow Studio 6.7.1

A 6.7.1 mantém **exatamente seis motores**. Coleta de evidência e benchmark pedagógico foram incorporados às fronteiras existentes.

## 1. Banco Editorial — `qf-editorial-engine-3`
Questões, proveniência, Curadoria, Projeto/Edital, legislação temporal e estados editoriais.

## 2. Learner Model — `qf-learner-engine-4`
FSRS/estado de aprendizagem, Knowledge Tracing, IRT, calibração, incerteza/abstenção, sinal de suporte do scaffolding e agora o **plano acionável de coleta de evidência** e o **benchmark pedagógico**.

Quando a evidência é insuficiente, o motor não força uma conclusão: explica o motivo e solicita observações diagnósticas.

## 3. Learning Engine — `qf-learning-engine-6`
Fila de estudo, precedência FSRS, recomendador multiobjetivo, simulados adaptativos, scaffolding operacional e agora **prática diagnóstica de coleta de evidência** restrita às questões do conceito-alvo.

## 4. Knowledge Engine — `qf-knowledge-engine-2`
RAG híbrido, grafo de conhecimento, chunks, evidências e contexto relacionado às questões.

## 5. AI Engine — `qf-ai-engine-4`
Tutor, AI Gateway, comentários, geração controlada e scaffolding progressivo. A 6.7.1 não exige novo modelo de IA para calcular o benchmark.

## 6. Evaluation & Governance — `qf-ai-governance-4`
Avaliação por afirmação/evidência, Questões Ouro, auditoria, telemetria e aprovação humana.

## Fluxo de coleta de evidência

`conceito com baixa evidência → plano de evidência → candidatos diagnósticos → mini-simulado → tentativa real → FSRS + KT + IRT → recalcular confiança → continuar ou encerrar`

A prática diagnóstica é identificada com origem própria (`coleta_evidencia`) e não é confundida com um envio do Telegram.

## Fluxo do benchmark pedagógico

`Sessão de scaffolding → nível/representação utilizados → tentativa posterior real → janela de retenção → grupo de apoio → métrica observacional`

O benchmark não altera o histórico original e não declara causalidade. Ele só produz leitura comparativa quando a amostra mínima é atingida.

## Infraestrutura transversal preservada

- Runtime Watchdog & Self-Healing;
- event loop assíncrono para I/O;
- rate limiting;
- Cloud Sync/Turso offline-first;
- Centro de Privacidade da IA;
- Structured Outputs e defesa contra prompt injection;
- versionamento e compatibilidade do runtime.
