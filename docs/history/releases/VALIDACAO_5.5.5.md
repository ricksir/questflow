# QuestFlow Studio 5.5.5 — Validação

## Nova área: Corrigir banco

A versão 5.5.5 adiciona uma área específica para manutenção de questões classificadas incorretamente durante a importação.

### Recursos validados

- filtro pelas matérias efetivamente existentes no banco;
- filtro por aula, status e busca textual/código;
- visualização das questões e abertura pela própria linha;
- correção rápida de matéria e aula;
- vínculo opcional com o conteúdo/tarefa exata da planilha de estudos;
- abertura do editor completo da questão para corrigir todos os campos já suportados pelo QuestFlow;
- exclusão da questão;
- preservação do UID e do histórico de respostas/envios ao mover uma questão;
- remoção das referências antigas de classificação quando a questão é movida;
- atualização da Cobertura dos estudos após mover, editar ou excluir;
- histórico interno das mudanças de classificação.

## Integridade da classificação

Quando uma tarefa/conteúdo exato da planilha é selecionado, o núcleo do QuestFlow resolve novamente a referência a partir da taxonomia atual antes de gravar. A matéria e a aula da tarefa selecionada se tornam a classificação de destino.

Quando a matéria/aula é corrigida sem selecionar uma tarefa exata, referências antigas que poderiam fazer a questão continuar contando no conteúdo anterior são removidas. O QuestFlow passa a recalcular a cobertura com a nova classificação.

## Testes

- Suíte automatizada completa: **221 testes executados / 221 aprovados**.
- Foram adicionados testes específicos para filtros SQL de matéria/aula, correção por tarefa exata, limpeza de referência antiga, mudança pelo editor completo e integração da nova interface/API.
- Chamada HTTP local para os novos métodos da API: validada.

## Diagnóstico

`diagnostico.py`: **Diagnóstico concluído sem falhas locais**.

O ambiente de validação Linux não possui Google Chrome, Selenium e pymupdf4llm instalados. O diagnóstico confirmou os fallbacks correspondentes. Telegram e Turso reais dependem da configuração do computador do usuário e não foram exercitados contra serviços reais nesta validação.
