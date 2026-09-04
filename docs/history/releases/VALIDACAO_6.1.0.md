# Validação — QuestFlow Studio 6.1.0

## Escopo

A versão 6.1.0 conclui a Etapa 3: **Tutor IA + diagnóstico inteligente de erros + arquitetura de seis motores + governança independente da IA**.

## Suíte automatizada

Resultado final:

- **276/276 testes aprovados**
- Python: compilação dos módulos concluída
- JavaScript: `node --check web/app.js` aprovado
- regressão HTTP da Curadoria mantida
- novos métodos da Etapa 3 incluídos na allowlist HTTP
- teste HTTP real da Etapa 3 aprovado

## Testes novos específicos da 6.1.0

Foram validados:

- registro de exatamente seis motores;
- inicialização da migração `ai_governance` v1;
- criação das tabelas de interações, avaliações e diagnósticos;
- diagnóstico por sinal comportamental (ex.: chute);
- precedência de erro informado pelo aluno (ex.: confusão conceitual);
- Tutor local fundamentado;
- persistência da interação como rascunho;
- avaliação independente da saída;
- aprovação humana explícita;
- detecção de referência legal não sustentada pelas evidências;
- Curadoria IA passando pelo mesmo Governance Engine;
- elementos da nova aba Tutor IA no frontend;
- acesso aos novos métodos pelo servidor HTTP local real.

## Migração real 6.0.0 → 6.1.0

Foi criada uma base usando o código original 6.0.0 com:

- 1 questão;
- 1 tentativa histórica;
- estado FSRS/KT/IRT existente.

A mesma base foi então aberta pela 6.1.0.

Resultado antes da geração do Tutor:

- questões preservadas: **1/1**;
- tentativas preservadas: **1/1**;
- arquitetura: **6 motores**;
- todos os motores: `ready`;
- nova migração: `ai_governance v1`;
- `PRAGMA quick_check`: **ok**;
- violações de foreign key: **0**.

Após uma execução local do Tutor:

- interações auditadas: **1**;
- avaliações independentes: **1**;
- diagnósticos: **1**;
- status da saída: **rascunho**;
- questões preservadas: **1**;
- tentativas preservadas: **1**;
- `PRAGMA quick_check`: **ok**;
- violações de foreign key: **0**.

## HTTP real com API completa

Usando `QuestFlowWebApi` + `QuestFlowLocalServer`, as seguintes chamadas retornaram HTTP 200, `ok=true`:

- `get_engine_architecture` — confirmou 6 motores;
- `get_tutor_workspace`;
- `get_ai_audit`.

## Política arquitetural

A arquitetura é um **monólito modular**. Os seis motores são independentes por responsabilidade e fronteira de código, mas não são seis microserviços separados. Esta escolha mantém transações locais, baixo overhead, portabilidade e operação offline-first.

## Política de IA

O AI Engine **não aprova sua própria saída**. O Evaluation & Governance Engine registra e avalia separadamente. Toda saída nasce como `rascunho` e a publicação/aprovação depende de ação humana explícita.
