# QuestFlow Studio 5.5.2 — Trilhas e planilha

## Base documental incorporada

A versão 5.5.2 registra uma base de conhecimento derivada dos seis documentos fornecidos: Trilhas 00 a 05. A sequência validada é 25 tarefas por documento: 1–25, 26–50, 51–75, 76–100, 101–125 e 126–150. Os números/matérias foram confrontados com o `CICLO_REG` do snapshot atual.

O programa mantém em `data/trail_guides.json` somente metadados estruturais, hashes e regras operacionais derivadas. Os PDFs completos não são copiados para o pacote.

## Lógica da planilha aprendida

A documentação e a aba `Instruções` estabelecem dois papéis principais. No **CICLO**, o aluno registra a execução das tarefas liberadas: DATA, CH EFETIVA, TOT QUEST FEITAS e TOT ACERTOS; o DESEMPENHO é calculado a partir desses dados. No **MAPA**, a evolução por aula é consolidada: T+R recebe SIM quando teoria e revisão terminam, e QTD EXE/ACERTOS alimentam desempenho e média.

Para a cobertura de questões, o QuestFlow usa o CICLO como fonte de execução real. Uma tarefa é considerada estudada quando há evidência em DATA, CH EFETIVA, TOT QUEST FEITAS ou TOT ACERTOS. A tela de cobertura cruza então matéria, aula, parte/conteúdo e banco de questões.

## Detecção de mudanças de layout

Os campos do CICLO não dependem mais exclusivamente das letras atuais das colunas. O leitor procura cabeçalhos semânticos como TRILHA, DATA, TAREFA, DISCIPLINA, CH (EFETIVA), TAREFAS/DESCRIÇÃO, TOT QUEST FEITAS/QTD EXE, ACERTOS e DESEMPENHO/DES (%). Também aceita os nomes de abas `CICLO_REG`/`CICLO` e `MAPA_AF`/`MAPA_AT`/`MAPA`.

## Regra de documentação faltante

A base inicial conhece somente as Trilhas 00 a 05. Se uma tarefa marcada como estudada pertencer a uma trilha sem documento cadastrado, `guide_status_for_tasks` agrupa a pendência por trilha, matérias e tarefas e gera o aviso. O usuário pode selecionar um ou vários PDFs no botão **Adicionar PDF explicativo da trilha**. A aplicação identifica o número da trilha e registra páginas, intervalo de tarefas, matérias e SHA-256.

No snapshot atual existem estudos nas Trilhas 00–07; por isso as Trilhas 06 e 07 aparecem como documentação faltante até que seus PDFs sejam adicionados.
