# Validação QuestFlow Studio 5.5.1

## Objetivo

Validar a nova análise de cobertura baseada exclusivamente nos conteúdos efetivamente estudados na aba `CICLO_REG`.

## Snapshot validado

- Planilha: `Trilhas00a18_AFRFB_Planilha de Controle`
- Tarefas de referência: 473
- Linhas com evidência de estudo no snapshot: 40
- Matérias estudadas identificadas: 5
- Evidências aceitas: DATA, CH EFETIVA, TOT QUEST FEITAS e TOT ACERTOS

## Regras validadas

1. Tarefa apenas planejada não entra na cobertura dos estudos.
2. `TOT QUEST FEITAS` é a referência quantitativa principal para o conteúdo realizado.
3. Se a quantidade estiver vazia, a lacuna é sinalizada sem meta inventada.
4. Questões do banco são comparadas por matéria + aula + conteúdo.
5. Partes diferentes da mesma aula não contam a mesma questão duas vezes.
6. Referência exata da classificação da planilha tem prioridade na associação.
7. Similaridade de conteúdo é usada apenas como fallback.
8. Falha de rede mantém disponível o último snapshot local válido.
9. A interface web sincroniza a planilha na primeira abertura da tela e permite sincronização manual.
10. A interface clássica usa a mesma semântica da interface web.

## Testes

- 203 testes automatizados: aprovados.
- Diagnóstico local: concluído sem falhas.
- Compilação Python dos módulos alterados: aprovada.
- Validação de sintaxe JavaScript: aprovada.
