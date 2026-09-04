# Validação técnica — QuestFlow Studio 6.6.5

## Correção reproduzida

O fluxo anterior podia manter questões na Curadoria depois de uma edição porque “Aprovada automaticamente” e “revisão humana concluída” eram conceitos ambíguos na interface. Além disso, o botão de conclusão podia confirmar sucesso sem verificar se a questão realmente havia saído da fila.

## Comportamento validado

1. Questão B autoaprovada permanece como revisão humana pendente.
2. O editor informa que aprovação automática não encerra a Curadoria humana.
3. “Salvar rascunho” persiste a edição e informa que a pendência permanece.
4. “Concluir revisão e retirar da pendência” persiste os dados e chama o validador real.
5. Se houver campo crítico faltante, a conclusão é recusada e o motivo é mostrado.
6. Se os requisitos críticos estiverem íntegros, a revisão humana é registrada e a questão sai da fila imediatamente.
7. A conclusão registra `curadoria.revisao_humana_concluida`, data e revisor.

## Testes

- 354/354 testes automatizados validados em partições.
- 145 arquivos Python compilados em memória sem erro.
- `node --check web/app.js`: aprovado.
- Testes específicos 6.6.5 cobrem autoaprovação, conclusão explícita e bloqueios críticos.
- Cloud Sync e demais regressões 6.6.x preservados.

## Banco

Nenhuma nova migração é necessária. A mudança utiliza campos JSON retrocompatíveis no registro da Curadoria.
