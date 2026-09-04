# QuestFlow Studio 6.6.1 — Arquitetura dos seis motores

A 6.6.1 mantém o QuestFlow como **monólito modular local-first** com exatamente seis fronteiras de domínio. Evaluation & Governance 2.0 amadurece uma fronteira existente; não cria um sétimo motor.

## 1. Banco Editorial — `qf-editorial-engine-3`

Responsável por questões, proveniência, curadoria, qualidade, atualidade, legislação temporal, Projeto de Concurso/Edital e vínculos editoriais.

## 2. Learner Model — `qf-learner-engine-2`

Responsável por FSRS, Knowledge Tracing, IRT pessoal, incerteza, abstenção e calibração probabilística.

## 3. Learning Engine — `qf-learning-engine-4`

Responsável por seleção pedagógica, recomendador multiobjetivo, simulados adaptativos, Central Hoje e planos orientados pelo estado do aluno, preservando a precedência FSRS.

## 4. Knowledge Engine — `qf-knowledge-engine-2`

Responsável por índice híbrido, RAG, chunks, grafo, recuperação de evidências e fontes temporais.

## 5. AI Engine — `qf-ai-engine-3`

Responsável por Tutor IA, comentários assistidos, geração controlada e AI Gateway multiprovedor. Pode gerar conteúdo, mas não aprová-lo.

## 6. Evaluation & Governance Engine — `qf-ai-governance-4`

Responsável por:

- auditoria da IA;
- decisão humana de aprovação/rejeição;
- telemetria e políticas de privacidade;
- avaliação independente;
- Questões Ouro;
- **avaliação por afirmação/evidência** da 6.6.1.

### Esteira 6.6.1

```text
Saída da IA
   ↓
Extrair afirmações verificáveis
   ↓
Para cada afirmação
   ├─ encontrar melhor evidência
   ├─ SUPORTA / CONTRADIZ / INSUFICIENTE
   ├─ conferir referência legal
   ├─ conferir vigência temporal
   └─ conferir gabarito oficial, quando disponível
   ↓
Resumo de grounding + alertas
   ↓
Persistência/auditoria
   ↓
Decisão humana quando o fluxo exigir publicação/aceitação
```

O conteúdo recuperado pelo Knowledge Engine continua tratado como dado, não como instrução privilegiada. O modelo gerador não possui autoridade para alterar o veredito de governança nem publicar automaticamente.

## Migrações vigentes

- `question_bank`: v8;
- `study`: v10;
- `ai_governance`: **v4**.

A migração v4 adiciona persistência de afirmações, evidências, expectativas de Questões Ouro e avaliação das execuções Ouro.
