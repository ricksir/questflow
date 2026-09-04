# Validação técnica — QuestFlow Studio 6.3.0

## Escopo

Validação da Etapa 5: geração controlada por fontes, legislação temporal, segundo crítico independente e questões ouro, preservando a arquitetura de seis motores e compatibilidade com a 6.2.0.

## Suíte automatizada

A suíte foi executada integralmente em quatro partições para evitar timeout do ambiente de CI local:

- partição 1: 74 testes — OK;
- partição 2: 63 testes — OK;
- partição 3: 88 testes — OK;
- partição 4: 71 testes — OK.

**Total: 296/296 testes aprovados.**

Os 11 testes específicos da Etapa 5 cobrem:

- rota HTTP local dos novos métodos;
- migrações `question_bank` v7 e `ai_governance` v2;
- permanência de exatamente seis motores;
- resolução temporal de legislação e indexação no RAG;
- recusa de geração sem fontes escolhidas;
- geração fundamentada e validação independente;
- bloqueio de publicação sem aprovação humana;
- bloqueio temporal para norma incompatível com a data da prova;
- uso do perfil de erros na formação de distratores;
- banco persistente de questões ouro e regressões;
- allowlist e wiring do frontend.

## Verificação estática

- 129 arquivos Python compilados via `py_compile`: OK.
- `node --check web/app.js`: OK.

## Migração real 6.2.0 → 6.3.0

Foi criada uma base usando o código original 6.2.0 com:

- 1 questão;
- 1 tentativa local de estudo;
- migrações `question_bank` 1–6;
- migrações `study` 1–9.

A mesma base foi aberta depois pela 6.3.0.

Resultado:

- questão preservada: 1/1;
- tentativa preservada: 1/1;
- `question_bank`: 1–7;
- `study`: 1–9;
- `ai_governance`: 1–2;
- motores ativos: 6;
- `PRAGMA quick_check`: `ok`;
- violações de foreign key: 0.

## Fluxo de segurança da geração

O caminho validado é:

`fontes selecionadas → snapshot → gerador → rascunho → crítico independente → decisão humana → publicação`

A geração sem fonte é recusada e uma saída validada ainda não é publicada sem aprovação humana explícita.

## Observação metodológica

O “segundo modelo” desta versão é um **crítico interno independente e determinístico** (`qf-generation-critic-1`), separado do gerador. Não é apresentado como um segundo fornecedor externo. Isso mantém avaliação reproduzível e funcionamento offline-first, deixando a arquitetura pronta para roteamento de modelos externos em evolução futura.
