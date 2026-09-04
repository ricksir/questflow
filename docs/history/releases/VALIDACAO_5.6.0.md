# QuestFlow Studio 5.6.0 — Validação

## Escopo

Revisão estrutural do motor de estudo, scheduler Telegram, integração com a planilha de estudos, armazenamento de estado de memória, configuração web/clássica e instalador.

## FSRS 6

- Dependência fixada em `fsrs[optimizer]==6.3.2`.
- Adapter usa a API pública `Scheduler`, `Card`, `Rating`, `ReviewLog` e `Optimizer`.
- Estados Learning/Review/Relearning persistidos no SQLite.
- 21 parâmetros personalizados e retenção ótima persistidos em `fsrs_optimizer_state`.
- Reprocessamento do histórico para criar ReviewLogs oficiais e reagendamento de cartões após otimização.
- Relearning automático e `Again/Hard/Good/Easy` inferidos do resultado, tempo e confiança informada.
- Retrievability usada na seleção vem do próprio Scheduler FSRS em lote; curva local é apenas fallback para cartões legados ainda não migrados.
- `ReviewLog.review_duration` recebe o tempo real de resposta em milissegundos.

## Seleção

Ordem rígida: correção > relearning vencido > revisão vencida > nova estudada > antecipada. A diversidade entre matérias é uma penalização suave, portanto matérias de maior risco podem receber mais itens sem formar blocos longos.

## Integração com estudos

A tabela `studied_scope` é reconstruída da taxonomia da planilha e limita o universo normal por matéria+aula quando `flow_studied_only` está ativo.

## Validação automatizada

`235 passed` na suíte completa após as alterações, incluindo cinco testes novos da 5.6.0 para precedência de vencimento, escopo estudado, metacognição, otimizador de 21 parâmetros e botões Telegram.

## Limitação do ambiente de construção

O ambiente de construção desta entrega não possui acesso de rede do `pip`, portanto a distribuição real de terceiros não pôde ser instalada nele. A API foi conferida com a documentação oficial atual e testada por contratos/mocks. Na máquina de destino, o instalador torna `fsrs[optimizer]==6.3.2` obrigatório e falha explicitamente se Scheduler/Card/Rating/ReviewLog/Optimizer não estiverem disponíveis.
