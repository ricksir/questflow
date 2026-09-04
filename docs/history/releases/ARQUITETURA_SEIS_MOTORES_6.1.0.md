# Arquitetura de Seis Motores — QuestFlow Studio 6.1.0

## Decisão arquitetural

O QuestFlow 6.1.0 adota um **monólito modular com seis motores independentes em responsabilidade**. Eles são módulos explícitos, possuem fronteiras próprias e são montados pelo `EngineRegistry`. Não são seis processos/microserviços: permanecem no mesmo processo local e usam o mesmo SQLite para preservar desempenho, transações atômicas, portabilidade e operação offline-first.

## Os seis motores

### 1. Banco Editorial — `EditorialBankEngine`

Responsável por questões, proveniência, qualidade editorial, inteligência individual, curadoria e decisão de duplicidade. Não contém lógica de aprendizado do aluno nem geração de IA.

### 2. Learner Model — `LearnerModelEngine`

Responsável pelo estado computacional do aluno: FSRS, Knowledge Tracing/BKT e IRT pessoal. Expõe estado por questão, dashboard e reconstrução a partir do histórico bruto.

### 3. Learning Engine — `LearningEngine`

Responsável pela evidência operacional de aprendizagem: tentativas, erros recentes, contexto de desempenho e preservação da precedência do scheduler. O FSRS continua sendo a autoridade para agenda/revisão.

### 4. Knowledge Engine — `KnowledgeEngine`

Responsável por RAG híbrido, índice semântico, chunks, grafo de conhecimento, recuperação de evidências e reindexação.

### 5. AI Engine — `AIEngine`

Responsável pelo Tutor IA, diagnóstico probabilístico de erros e assistência editorial. Recebe dados dos outros motores, mas não aprova a própria saída.

Modos do Tutor: Rápido, Professor, Socrático e Banca.

O contexto pode combinar: questão editorial + tentativa recente + FSRS + KT + IRT + diagnóstico + RAG + grafo.

### 6. Evaluation & Governance Engine — `EvaluationGovernanceEngine`

Responsável por auditoria e avaliação independente da IA. Persiste interação, prompt/hash, provedor/modelo, fontes, contexto, diagnóstico, resposta, avaliação e revisão humana.

Nenhuma saída do AI Engine é automaticamente aprovada. O estado inicial é `rascunho`.

## Fluxo da Etapa 3

```text
Banco Editorial ───────┐
Learner Model ─────────┤
Learning Engine ───────┼──> AI Engine ──> rascunho
Knowledge Engine ──────┘                    │
                                            v
                         Evaluation & Governance Engine
                                            │
                              avaliar + auditar + sinalizar
                                            │
                                            v
                                   revisão humana
                               aprovar / rejeitar / manter
```

## Regras de dependência

- A interface web não calcula diagnóstico pedagógico.
- A API local orquestra chamadas, mas regras da Etapa 3 ficam nos motores.
- O AI Engine não persiste aprovação por conta própria.
- O motor de governança não gera conteúdo.
- O Knowledge Engine não altera o modelo do aluno.
- O Learner Model não altera evidências editoriais.
- FSRS não é substituído pelo Tutor ou pela IRT.
- Curadoria e Tutor compartilham a mesma política de governança da IA.

## Migrações

A 6.1.0 preserva `question_bank` v1–v6 e `study` v1–v8. Adiciona o componente independente:

- `ai_governance` v1

Tabelas principais:

- `qf_ai_interactions`
- `qf_ai_evaluations`
- `qf_error_diagnoses`

A migração é incremental e idempotente.
