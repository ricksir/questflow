# Arquitetura de Seis Motores — QuestFlow Studio 6.2.0

A versão 6.2.0 mantém o QuestFlow como **monólito modular offline-first com exatamente seis motores independentes em responsabilidade**. A Etapa 4 não cria um sétimo “motor de recomendação”: recomendação e simulados são responsabilidades do **Learning Engine**, que consome sinais dos demais motores.

## 1. Banco Editorial

Responsável por questões, proveniência, revisão, qualidade, direitos, dificuldade empírica e candidatos a duplicidade. Continua sendo a fonte editorial da questão.

## 2. Learner Model

Responsável pelo estado computacional do aluno: **FSRS + Bayesian Knowledge Tracing + IRT pessoal**. Produz sinais como recuperabilidade, domínio/confiança, habilidade, dificuldade e informação do item.

## 3. Learning Engine — evoluído na Etapa 4

Responsável pela decisão pedagógica e execução da prática. Na 6.2.0 incorpora:

- recomendador multiobjetivo `qf-multiobjective-1`;
- perfis Equilibrado, Diagnóstico, Revisão e Cobertura do edital;
- precedência rígida das classes FSRS;
- diversificação por matéria, aula, assunto e banca;
- simulados adaptativos questão a questão;
- projeções por matéria com intervalo de confiança;
- registro de prática local no mesmo histórico do modelo do aluno, com origem distinta do Telegram.

O fluxo de decisão é:

`FSRS define a classe elegível → sinais KT/IRT/cobertura/banca/urgência compõem o score → diversidade escolhe o item → resposta atualiza FSRS+KT+IRT → próxima questão é recalculada`.

## 4. Knowledge Engine

Responsável pelo RAG híbrido, índice semântico, chunks e grafo de conhecimento. Fornece contexto e relações sem assumir a decisão de agenda.

## 5. AI Engine

Responsável pelo Tutor e composição assistida. Continua sem autoridade para aprovar conteúdo nem alterar a precedência do scheduler.

## 6. Evaluation & Governance Engine

Responsável por avaliação independente, auditoria, aprovação/rejeição humana e rastreabilidade das saídas de IA.

## Regras arquiteturais preservadas

1. **FSRS precedence**: score global não permite que um item menos urgente atravesse uma classe superior de revisão.
2. **Offline-first**: recomendação e simulados funcionam sem serviço externo.
3. **Dados derivados reconstruíveis**: KT/IRT, índices e projeções derivam de histórico persistido.
4. **Sem falsa precisão**: incidência de banca é rotulada como observada no banco local; projeção de acerto não é apresentada como chance de aprovação.
5. **Uma tentativa, um histórico de aprendizagem**: Telegram e simulado alimentam o mesmo Learner Model, distinguindo a origem da interação.
6. **Seis motores, não seis microserviços**: as fronteiras são explícitas, mas permanecem no mesmo processo/SQLite para manter consistência transacional e simplicidade operacional.

## Persistência da Etapa 4

A migração `study` v9 adiciona:

- `source` em `telegram_deliveries` e `telegram_attempts`;
- `adaptive_simulation_sessions`;
- `adaptive_simulation_items`.

As sessões e itens adaptativos entram no Cloud Sync como estado de aprendizagem. O histórico operacional de Telegram filtra `source=telegram`, portanto tentativas de simulado não aparecem como envios do bot.
