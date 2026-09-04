# QuestFlow Studio 5.5.1 — Cobertura dos estudos

A tela **Estudos e questões > Cobertura dos estudos** usa a aba `CICLO_REG` como fonte do que foi efetivamente estudado.

## Quando uma tarefa é considerada estudada

Uma linha é analisada quando existir evidência real de execução: CH efetiva, quantidade de questões feitas, acertos ou data registrada. Linhas apenas planejadas permanecem fora da lista.

## Campos usados

- TRILHA
- DATA
- TAREFA
- DISCIPLINA
- CH planejada
- CH EFETIVA
- descrição da TAREFA
- TOT QUEST FEITAS
- TOT ACERTOS
- DESEMPENHO
- aula e segmentos de conteúdo extraídos da descrição

## Como a lacuna é calculada

Quando `TOT QUEST FEITAS` possui valor, ele é usado como referência de quantidade para aquele conteúdo estudado. O QuestFlow compara essa quantidade com as questões já cadastradas que correspondem à mesma matéria, aula e conteúdo.

`Faltam adicionar = max(0, questões feitas na planilha - questões correspondentes no banco)`

Quando não existe quantidade explícita na planilha, o sistema apenas informa que o conteúdo estudado está sem cobertura, sem criar uma meta artificial.

## Como evita duplicidade

Se várias tarefas pertencem à mesma aula, cada questão do banco é atribuída a apenas um conteúdo. A associação prioriza a referência exata da classificação da planilha e usa similaridade de assunto como fallback.

## Sincronização

Ao abrir a tela pela primeira vez na sessão, o QuestFlow tenta atualizar a planilha Google. O botão **Sincronizar planilha** força nova leitura. Se Google/proxy estiver indisponível, o último snapshot local continua sendo exibido.
