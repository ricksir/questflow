# Instruções de atualização — QuestFlow Studio 6.18.1 / Mobile 0.13.1

## Ordem recomendada

1. Feche o QuestFlow Studio.
2. Aplique `QuestFlow_Studio_6.18.1_UPDATE.zip` pelo atualizador normal.
3. Abra o Studio e confirme **Versão 6.18.1**.
4. Execute `ATUALIZAR_QUESTFLOW_MOBILE_0.13.1.bat`.
5. Abra o Mobile e confirme **0.13.1**.
6. Sincronize uma vez com o Studio.

## O que verificar

### Studio

Na lateral deve aparecer **Correções e Matérias não Estudadas**. Dentro da tela:

- parte superior: **Correções**;
- parte inferior: **Matérias ainda não estudadas**.

Uma marcação “ainda não estudado” não deve aparecer na tabela de Correções.

### Mobile offline

Ao terminar uma sessão com respostas ainda sem feedback do Studio, o resumo deve mostrar o número de questões respondidas e a quantidade **Aguardando correção**. O percentual de acerto só aparece depois que houver resultados corrigidos.

## Preservação

O update do Studio não inclui `data`, `mobile`, `node_modules`, `.expo` ou caches. O atualizador Mobile preserva `node_modules`, `.expo`, Android/iOS nativos e cria backup das fontes antes da troca.
