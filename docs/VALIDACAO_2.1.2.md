# Validação - QuestFlow Studio 2.1.2

Data da validação: 15/07/2026.

## Objetivo

Validar o novo extrator multiformato com o arquivo `tecinformacao1.pdf`, cujo layout é diferente dos PDFs do QConcursos anteriormente suportados.

O documento possui:

- título `LISTA DE QUESTÕES`;
- metadados no padrão `(BANCA / ÓRGÃO - ANO)`;
- questões de múltipla escolha e de Certo/Errado;
- enunciados e alternativas que continuam em páginas seguintes;
- questões dependentes de figuras;
- página final denominada `GABARITO`;
- respostas escritas como `LETRA A-E`, `CORRETO` e `ERRADO`.

## Resultado obtido

- Modo selecionado: `texto_nativo_lista_gabarito`;
- Questões identificadas: **24**;
- Gabaritos identificados e associados: **24**;
- Questões de múltipla escolha: **15**;
- Questões de Certo/Errado: **9**;
- Questões inseridas em banco SQLite limpo: **24**;
- Duplicatas no banco de teste: **0**;
- Matéria atribuída: **FLUÊNCIA EM DADOS**;
- Aula da planilha atribuída: **Aula 06**;
- Assunto atribuído: **Sistemas de Suporte à Decisão, Data Warehouse, Business Intelligence e ETL**.

As questões 12 e 16 foram extraídas com enunciado, alternativas e gabarito, mas ficaram com status **pendente**, porque fazem referência a figuras do PDF e precisam de conferência visual antes do envio automático.

## Continuidade entre páginas

Foram verificados os seguintes casos:

- questão 6 iniciada na página 1 e concluída na página 2;
- questão 12 iniciada na página 2 e concluída na página 3;
- questão 16 iniciada na página 3 e concluída na página 4;
- questão 24 iniciada na página 5 e com a última alternativa na página 6.

Todos esses casos foram unidos corretamente pelo extrator.

## Regressão do formato anterior

O arquivo `auditoria8.pdf`, no formato visual do QConcursos, continuou sendo processado pelo extrator OCR anterior, com:

- 5 questões identificadas;
- 5 gabaritos associados;
- alternativas de múltipla escolha e Certo/Errado reconhecidas no DPI padrão de 180.

## Diagnóstico local

O script `diagnostico.py` foi ampliado com a criação automática de um PDF textual sintético contendo:

- uma questão de múltipla escolha;
- uma questão de Certo/Errado;
- metadados de banca, órgão e ano;
- página de gabarito.

O diagnóstico foi concluído sem falhas locais.

## Limite conhecido

Quando uma questão depende de figura, gráfico ou diagrama, o texto, as alternativas e o gabarito são extraídos, mas a questão fica pendente para conferência visual. Isso impede que uma questão incompleta seja aprovada silenciosamente e enviada ao Telegram.
