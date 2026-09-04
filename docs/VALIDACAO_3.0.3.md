# Validação técnica — QuestFlow Studio 3.0.3

## Escopo

Validação da pesquisa web refinada, transcrição segura de campos faltantes e retirada de questões anuladas da base ativa.

## Pesquisa web

Foram testados:

- geração de consultas com código e trechos do enunciado;
- parser de resultados Google;
- parsers Bing, DuckDuckGo e DuckDuckGo Lite;
- validação de código exato mais similaridade do enunciado;
- rejeição de uma página com o mesmo código, porém enunciado diferente;
- extração de ano, banca, órgão, alternativas e gabarito;
- preenchimento apenas de campos vazios ou incompletos;
- montagem do payload do Telegram após o preenchimento.

O ambiente de testes não permitiu uma consulta DNS ao vivo durante a execução Python. Por isso, a parte online foi validada com páginas HTML representativas e a pesquisa externa da questão de exemplo foi conferida separadamente. No computador do usuário, a disponibilidade continua dependendo da internet e dos mecanismos de busca.

## Questões anuladas

Foi validado que uma questão marcada como anulada:

- é removida da tabela ativa `questions`;
- deixa de aparecer nas estatísticas da base ativa;
- é preservada em `excluded_questions` com motivo e data;
- não é reinserida por nova importação do mesmo código ou fingerprint.

## Testes automatizados

Resultado: **29 testes aprovados**.

Arquivo completo: `docs/RESULTADO_TESTES_3.0.3.txt`.

## Diagnóstico integrado

O diagnóstico verificou dependências, Tesseract, pipeline Markdown, PDFs textuais, análise apurada, banco, estudo, Telegram, agendamento, pesquisa web, anuladas e consistência da versão.

Resultado: **sem falhas locais**.

Arquivo completo: `docs/RESULTADO_DIAGNOSTICO_3.0.3.txt`.

## Teste gráfico

A interface foi criada em monitor virtual. A escala aumentou de 10 para 12 pontos sem reiniciar, e os controles de seleção múltipla, análise em lote e pesquisa web estavam disponíveis.

Arquivo: `docs/RESULTADO_TESTE_INTERFACE_3.0.3.txt`.

## Limites

- A conexão real com o Telegram exige token e Chat ID do usuário.
- Sites podem bloquear automação, alterar o HTML ou exigir autenticação.
- O programa não contorna login, paywall ou proteção de acesso.
- Resultados web permanecem registrados para revisão e não devem substituir a conferência humana quando houver divergência.
