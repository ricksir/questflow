# Validação QuestFlow Studio 3.0.4

## Objetivo

Validar a pesquisa web sequencial solicitada: código isolado, fallback por enunciado isolado, confirmação por banca e ano e leitura do gabarito na página aberta.

## Regras implementadas

- consulta inicial: apenas `"Q########"`;
- nenhuma consulta combina código e enunciado;
- fallback: apenas trecho exato ou palavras significativas do enunciado;
- banca e ano não entram na consulta: são usados para validar o conteúdo da página;
- snippet de buscador não confirma a questão;
- a página precisa ser baixada e interpretada pelo QuestFlow;
- gabarito só é aplicado quando aparece em página cuja questão, banca e ano foram confirmados;
- se a busca por código confirmar a questão, mas não encontrar o gabarito, o fallback por enunciado é executado para tentar localizar uma fonte completa.

## Testes

A suíte completa executou 33 testes, incluindo:

- código isolado sem enunciado, banca ou ano;
- enunciado isolado sem código ou metadados;
- interrupção do fallback quando a busca por código confirma questão e gabarito;
- fallback após resultado de código incorreto;
- fallback para localizar gabarito ausente;
- rejeição de mesma questão com banca diferente;
- rejeição de snippet como fonte confirmada;
- leitura de alternativas, metadados e gabarito em página simulada;
- regressões de extração, Telegram, banco, Markdown e estudo adaptativo.

Resultado: `Ran 33 tests` / `OK`.

O diagnóstico integrado e o teste gráfico da interface também foram concluídos sem falhas locais. A pesquisa ao vivo depende da internet, da disponibilidade do mecanismo de busca e de o site permitir leitura automatizada.
