# Validação — QuestFlow Studio 5.5.3

## Importação contextual da cobertura dos estudos

A versão 5.5.3 acrescenta um fluxo direto entre **Estudos e questões > Cobertura dos estudos** e **Importar**.

### Comportamento validado

- Conteúdos pendentes exibem a ação **Adicionar PDF**.
- O número em **Faltam adicionar** também é clicável.
- A seleção abre a tela de importação com contexto visível de trilha, tarefa, matéria, aula e conteúdo.
- O seletor contextual restringe a escolha a PDFs.
- O navegador envia o `task_id`; o núcleo reconstrói os metadados autoritativos a partir da cobertura atual antes de importar.
- Matéria e aula são vinculadas ao lote escolhido.
- A referência exata da tarefa é gravada em `classificacao_planilha.referencia`, permitindo que a cobertura atribua cada questão ao conteúdo selecionado mesmo quando há várias partes da mesma aula.
- O extrator normal continua responsável por código, enunciado, alternativas, gabarito, banca, ano e tópicos específicos.
- Após a importação, a cobertura daquele `task_id` é recalculada e a interface informa a quantidade restante quando a planilha possui uma meta numérica.
- O contexto é limpo depois da conclusão para evitar herança acidental em uma importação posterior.
- A importação comum, aberta diretamente pelo menu, permanece sem vínculo contextual.

## Testes

- 214 testes automatizados: **214 aprovados**.
- 4 testes novos cobrem especificamente resolução segura do contexto, vinculação no banco, filtro de PDF e presença dos controles na interface web.
- `web/app.js` validado por `node --check`.
- `web_api.py` validado por `py_compile`.
- Diagnóstico QuestFlow: **concluído sem falhas locais**.

Limitações do ambiente de validação: Google Chrome, Telegram real e Turso real não estão configurados no contêiner de testes. O núcleo local, banco SQLite, API HTTP/JSON e lógica de importação contextual foram validados localmente.
