# Validação — QuestFlow Studio 6.2.0

## Escopo

A 6.2.0 conclui a Etapa 4: **Recomendador Multiobjetivo + Simulados Adaptativos**, mantendo a arquitetura de seis motores e a precedência do FSRS.

## Testes específicos da Etapa 4

Foram adicionados 9 testes dedicados para validar:

- pesos diferentes dos perfis de recomendação;
- decomposição explicável do score;
- intervalo de Wilson e projeção combinada;
- migração `study` v9 e novas tabelas/colunas;
- dashboard de recomendação, projeções e bancas;
- seleção adaptativa somente depois da atualização FSRS + KT + IRT;
- não repetição da mesma questão na sessão;
- isolamento do histórico operacional do Telegram;
- manutenção de exatamente seis motores;
- allowlist/frontend da Etapa 4;
- chamadas sobre HTTP loopback real.

## Suíte de regressão

O discovery atual contém **285 testes**. Todos os 285 foram executados e aprovados durante a validação, em partições da mesma suíte para respeitar o limite de execução do ambiente. Não foram observados `FAIL` ou `ERROR`.

A verificação inclui regressões de importação, FSRS, Learning Analytics, Learner Model, Curadoria/RAG, Tutor IA, Turso Cloud Sync, Telegram, reset, banco, API web e interface.

## Migração real 6.1.0 → 6.2.0

Foi usada a distribuição original 6.1.0 para criar uma base SQLite com:

- 7 questões aprovadas;
- 3 tentativas anteriores;
- `study` v1–v8;
- Learner Model já alimentado.

A mesma base foi então aberta pela 6.2.0. Resultado antes do primeiro simulado:

- questões preservadas: **7/7**;
- tentativas preservadas: **3/3**;
- migrações `study`: **v1–v9**;
- tabelas adaptativas criadas: **2/2**;
- `PRAGMA quick_check`: **ok**;
- violações de foreign key: **0**;
- arquitetura: **6 motores**.

Em seguida foi iniciado um simulado diagnóstico de 5 questões. Após a primeira resposta:

- foi criada 1 tentativa com `source=simulado_adaptativo`;
- FSRS/KT/IRT foram atualizados;
- a próxima questão escolhida foi diferente da anterior;
- o banco permaneceu com `quick_check=ok` e zero violações de FK.

## Validações estáticas

- módulos Python alterados compilados com sucesso;
- `web/app.js` aprovado em `node --check`;
- API HTTP da Etapa 4 está na allowlist do servidor local;
- testes anteriores que comparam todas as chamadas `bridge.call(...)` com a allowlist continuam aprovados.

## Observações metodológicas

- O score multiobjetivo só ordena dentro da classe elegível definida pelo scheduler; ele não substitui o FSRS.
- A incidência da banca deriva do banco local e é rotulada como tal.
- A IRT é pessoal/regularizada.
- A projeção possui intervalo de confiança e não é rotulada como probabilidade de aprovação.

## Smoke test da API real

Também foi instanciada a `QuestFlowWebApi` real sobre um SQLite temporário com seis questões aprovadas. O teste confirmou:

- `get_recommendation_dashboard`: `ok=true`, 6 recomendações;
- `start_adaptive_simulation`: `ok=true`;
- após uma resposta, `answered_count=1` e uma nova questão já estava selecionada;
- `get_engine_architecture`: 6 motores.
