# Arquitetura de seis motores — QuestFlow Studio 6.5.0

A 6.5.0 mantém um **monólito modular offline-first com exatamente seis motores**, evitando microserviços desnecessários e preservando transações locais.

## 1. Banco Editorial — `qf-editorial-engine-3`
Responsável por questões, proveniência, curadoria, legislação temporal, Projeto de Concurso/Edital, retificações, vínculos questão↔edital e estado temporal.

## 2. Learner Model — `qf-learner-engine-1`
Mantém FSRS, Knowledge Tracing e IRT pessoal. Produz domínio, confiança, memória e informação psicométrica sem controlar sozinho o conteúdo editorial.

## 3. Learning Engine — `qf-learning-engine-3`
Orquestra estudo, recomendador, simulados e a Central “O que fazer hoje?”. O projeto ativo contextualiza a decisão, mas a precedência FSRS continua superior.

## 4. Knowledge Engine — `qf-knowledge-engine-2`
Mantém RAG híbrido, chunks, índice semântico, grafo e fontes selecionadas. A legislação temporal continua disponível como conhecimento versionado.

## 5. AI Engine — `qf-ai-engine-2`
Tutor, comentários assistidos e geração controlada multiprovedor. Continua sem autoridade para aprovar a própria saída.

## 6. Evaluation & Governance Engine — `qf-ai-governance-2`
Avaliação independente, auditoria, aprovação humana, perfil de erros, questões ouro e regressão.

## Fluxo central 6.5.0

`Projeto ativo → edital vigente → itens programáticos → vínculo com banco → cobertura/KT/IRT/FSRS → Learning Engine → O que fazer hoje?`

## Princípios preservados

- offline-first;
- human-in-the-loop;
- IA auditável;
- precedência FSRS;
- RAG fundamentado;
- migrações incrementais;
- geração separada de avaliação;
- recomendação multiobjetivo;
- legislação e edital versionados;
- estado temporal explícito das questões.
