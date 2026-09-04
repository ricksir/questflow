# Validação QuestFlow Studio 3.0.6

## Escopo

Validação da nova pesquisa exclusivamente pelo Google, com navegador visível e leitura da página renderizada.

## Testes executados

- construção da consulta por código com a pergunta orientadora solicitada;
- fallback pelo enunciado sem misturar código, banca ou ano na consulta;
- leitura do bloco “Informações da Questão” da página do Google;
- extração de banca, ano, órgão, enunciado, gabarito e justificativa;
- normalização de gabarito `ERRADO` para `E`;
- confirmação por código exato, banca e ano;
- abertura de cinco resultados adicionais quando a página do Google está incompleta;
- preenchimento seguro apenas de campos vazios;
- compilação dos módulos;
- diagnóstico integrado;
- teste gráfico da interface em monitor virtual;
- suíte completa com 35 testes automatizados.

## Resultados

- 35 testes automatizados: **OK**;
- diagnóstico integrado: **sem falhas locais**;
- teste gráfico: **OK**;
- parser da página renderizada do Google: **OK**;
- confirmação de gabarito e justificativa em conteúdo de referência: **OK**.

## Limitação do ambiente de validação

O ambiente de construção não possuía um ChromeDriver utilizável para uma consulta real ao Google. A abertura do navegador foi validada por testes de integração simulados, e o instalador inclui Selenium para que o Selenium Manager localize ou obtenha o driver compatível no Windows. A consulta real deve ser confirmada no computador do usuário, podendo ser afetada por CAPTCHA, consentimento, login ou mudanças no HTML do Google.
