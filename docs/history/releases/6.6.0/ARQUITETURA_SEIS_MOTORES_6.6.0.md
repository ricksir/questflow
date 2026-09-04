# Arquitetura dos seis motores — QuestFlow Studio 6.6.0

A 6.6.0 mantém o **monólito modular com exatamente seis motores**. Não foi criado um “Calibration Engine” ou “Uncertainty Engine”.

1. **Banco Editorial — `qf-editorial-engine-3`**  
   Questões, proveniência, curadoria, legislação temporal, Projeto/Edital e atualidade.

2. **Learner Model — `qf-learner-engine-2`**  
   FSRS + BKT/Knowledge Tracing + IRT pessoal + predição seletiva + incerteza + calibração + planos contrafactuais.

3. **Learning Engine — `qf-learning-engine-4`**  
   Recomendação, simulados adaptativos, Central Hoje e seleção diagnóstica orientada por incerteza, sempre dentro da precedência FSRS.

4. **Knowledge Engine — `qf-knowledge-engine-2`**  
   RAG híbrido, grafo, chunks, legislação versionada e fontes selecionadas.

5. **AI Engine — `qf-ai-engine-3`**  
   Tutor, comentários, geração controlada e AI Gateway. O Tutor respeita a abstenção do Learner Model.

6. **Evaluation & Governance Engine — `qf-ai-governance-3`**  
   Avaliação independente, auditoria, aprovação humana, Questões Ouro, privacidade e observabilidade da IA.

## Fluxo de incerteza

`Resposta histórica → previsão pré-resposta → confiança/intervalo → abster ou aceitar → resultado real → calibração → nova seleção diagnóstica`

A abstenção não apaga a estimativa interna; ela controla como a estimativa pode ser usada e apresentada.

## Princípios preservados

- offline-first;
- FSRS precedence;
- human-in-the-loop;
- RAG grounding;
- incremental migrations;
- privacy minimization;
- structured outputs;
- selective prediction;
- calibration monitoring;
- counterfactual learning plans.
