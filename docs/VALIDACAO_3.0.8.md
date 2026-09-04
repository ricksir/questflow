# Validação QuestFlow Studio 3.0.8

## Problema corrigido

A Visão Geral do Google apresentava parte das informações da questão recolhida atrás do botão **Mostrar mais**. O QuestFlow lia a página antes de expandir esse conteúdo e, por isso, podia informar que gabarito ou justificativa não estavam disponíveis.

## Solução implementada

1. aguardar a página de pesquisa renderizar;
2. localizar controles visíveis com os textos Mostrar mais, Ver mais, Mostrar tudo, Mais detalhes, Show more ou See more;
3. rolar o controle para o centro da tela;
4. clicar normalmente e usar clique JavaScript como contingência;
5. aguardar o texto da página crescer;
6. aguardar o DOM estabilizar;
7. somente então interpretar código, banca, ano, enunciado, gabarito e justificativa;
8. interromper novos cliques quando gabarito e justificativa já estiverem visíveis.

## Testes

- 39 testes automatizados aprovados;
- teste unitário específico para clicar em Mostrar mais;
- teste de leitura de gabarito e justificativa após a expansão;
- compilação de todos os módulos;
- diagnóstico integrado sem falhas;
- teste gráfico da interface em monitor virtual.

## Limite do ambiente de construção

A navegação ao vivo no Google não pôde ser executada neste ambiente porque não havia um ChromeDriver disponível. A rotina de clique e crescimento do conteúdo foi validada com um navegador simulado e o fluxo completo de extração foi validado por testes automatizados. No Windows, o programa usa Selenium Manager com Chrome ou Edge, como nas versões anteriores.
