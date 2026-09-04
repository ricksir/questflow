# QuestFlow Studio 5.5.7 - Validação

## Regressão com PDF real QConcursos

Arquivo analisado externamente durante o desenvolvimento: `fluencia-dados_Aula01.pdf`.
O arquivo não é redistribuído dentro do QuestFlow.

Resultados do novo leitor nativo:

- 20 questões detectadas;
- 20 códigos Qxxxx preservados;
- 20/20 gabaritos reconhecidos pelo bloco nativo `Respostas`;
- enunciados recompostos inclusive quando atravessam páginas;
- alternativas textuais separadas pelas coordenadas reais da página;
- banca, órgão, ano e prova lidos sem OCR;
- 19 questões textuais completas e 1 questão visual marcada para revisão;
- a questão visual recebeu recorte automático das alternativas/diagramas;
- o nome `fluencia-dados_Aula01.pdf`, com a taxonomia AFRFB, classifica o lote como `FLUÊNCIA EM DADOS / Aula 01` antes de eventual contexto autoritativo da tela Estudos e questões;
- tempo observado no ambiente de validação: aproximadamente 1,4 s para as 10 páginas, sem OCR.

## Reparo de importação antiga

Foi validado o fluxo em que um Qxxxx já existente possuía enunciado vazio,
alternativas vazias e gabarito ausente. Ao reimportar o mesmo código pelo novo
parser, o registro foi reparado no próprio UID (`repaired = 1`) e não criado como
duplicata.

## Testes automatizados

- 230 testes executados;
- 230 aprovados;
- 4 testes novos da 5.5.7 cobrem ordem visual do QConcursos, metadados fora da
  ordem interna, dica matéria/aula pelo nome do arquivo e reparo de duplicata quebrada.

## Integração com Estudos e questões

O PDF real também foi processado por um contexto de importação agrupada de
`FLUÊNCIA EM DADOS / Aula 01` e gravado em banco temporário:

- 20 extraídas;
- 20 inseridas;
- todas as 20 com matéria `FLUÊNCIA EM DADOS`;
- todas as 20 com aula `Aula 01`;
- 20 com enunciado + alternativas + gabarito estruturalmente completos;
- 1 permaneceu pendente exclusivamente por possuir alternativas visuais.
