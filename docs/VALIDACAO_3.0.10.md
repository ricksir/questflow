# Validação QuestFlow Studio 3.0.10

## Escopo

- Google Modo IA como única fonte da pesquisa assistida;
- nenhuma abertura de resultado externo;
- leitura da resposta renderizada e expansão de `Mostrar mais`;
- confirmação por código/enunciado, banca e ano;
- extração de enunciado, alternativas, gabarito e justificativa;
- prévia Telegram antes de qualquer alteração no banco;
- confirmação ou cancelamento explícito pelo usuário.

## Testes realizados

- 42 testes automatizados: **OK**;
- compilação de `app.py`, `diagnostico.py` e módulos `core`: **OK**;
- diagnóstico integrado: **sem falhas locais**;
- teste gráfico em monitor virtual: **OK**;
- teste de parsing do formato `Informações Gerais / Enunciado da Questão / Alternativas / Gabarito / Justificativa`: **OK**;
- teste de página incompleta: duas tentativas (código e enunciado), sem abrir links externos: **OK**;
- teste de CAPTCHA manual e tempo de espera: **OK**;
- teste de expansão de `Mostrar mais`: **OK**.

## Limitação de validação

A navegação ao vivo no Modo IA depende da conta, região, disponibilidade do recurso,
Chrome/Edge, conexão e eventuais verificações do Google. A rotina foi validada por
testes simulados de DOM e pela inicialização gráfica do aplicativo; o teste final da
conta real deve ser feito no computador do usuário.
