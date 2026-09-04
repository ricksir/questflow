# Validação técnica — QuestFlow Studio 6.6.6

## Escopo
Curadoria com navegação guiada até o campo exato responsável por uma pendência editorial.

## Resultado
- **357/357 testes automatizados aprovados**.
- Partições: **109 + 126 + 122 = 357**.
- `node --check web/app.js`: aprovado.
- Compilação Python: aprovada.
- Regressão de Curadoria 6.6.4/6.6.5: aprovada.
- Regressão de Cloud Sync 5.4/6.5.2/6.6.2: aprovada.

## Cenários específicos validados
1. `Enunciado íntegro` aponta para `#statementInput`.
2. `Gabarito consistente` aponta para `#field-gabarito`.
3. `Alternativas estruturadas` aponta para a seção de alternativas.
4. Matéria e assunto apontam para seus campos de classificação.
5. O elemento de destino recebe `scrollIntoView`, foco e realce temporário.
6. Falha ao concluir revisão renderiza ações `Ir ao campo` no rodapé.
7. A fila de Curadoria consegue abrir a questão já direcionada ao requisito selecionado.
8. A navegação guiada não altera banco, FSRS, KT, IRT ou Cloud Sync.

## Banco
Sem migração nova:
- question_bank: v8
- study: v10
- ai_governance: v4
