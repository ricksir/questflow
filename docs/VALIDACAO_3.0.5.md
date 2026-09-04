# Validação QuestFlow Studio 3.0.5

## Objetivo

Validar a pesquisa web sequencial solicitada para questões pendentes, com abertura real das páginas encontradas, confirmação por banca/ano/enunciado e recuperação de gabarito e justificativa.

## Fluxo validado

1. Consulta pelo código no formato `"Q2096379" qual o texto da questão, gabarito e justificativa?`.
2. Abertura sequencial de pelo menos cinco páginas, quando disponíveis.
3. Continuação até dez páginas quando nenhuma das cinco primeiras confirma a questão.
4. Fallback para o enunciado, sem misturar código, banca ou ano na consulta.
5. Confirmação da banca, do ano e da semelhança do enunciado na página aberta.
6. Extração de enunciado, alternativas, gabarito e justificativa.
7. Preenchimento somente de campos ausentes ou incompletos.

## Melhorias técnicas

- Fallback Bing RSS para situações em que os mecanismos HTML bloqueiam a leitura automática.
- Busca de gabarito em texto visível, JSON embutido e atributos HTML.
- Extração de blocos de `Justificativa`, `Comentário do professor`, `Gabarito comentado`, `Explicação`, `Resolução` e `Fundamentação`.
- Registro de cada endereço tentado, mecanismo, abertura, confirmação, gabarito e justificativa encontrados.
- Snippets de buscadores continuam sendo apenas informativos: não confirmam a questão nem o gabarito.

## Testes

A suíte automatizada executou 36 testes, incluindo:

- ordem das consultas;
- frase orientadora após código e enunciado;
- abertura de cinco links;
- continuação quando não há confirmação;
- rejeição por banca ou ano divergente;
- fallback pelo enunciado;
- leitura de gabarito somente na página aberta;
- extração e aplicação da justificativa;
- parser de Google, Bing, Bing RSS, DuckDuckGo e DuckDuckGo Lite;
- regressão do OCR, Markdown, Telegram, banco, anulação e repetição adaptativa.

Resultado: **36 testes aprovados** e diagnóstico local sem falhas.

## Limitação externa

A pesquisa depende de conexão com a internet e das páginas permitirem leitura automatizada. Sites que exigem login, CAPTCHA ou carregamento exclusivamente por JavaScript podem impedir a transcrição automática; nesses casos, os endereços continuam disponíveis para abertura manual.
