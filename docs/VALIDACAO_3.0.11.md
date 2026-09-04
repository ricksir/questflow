# Validação QuestFlow Studio 3.0.11

## Escopo

Otimização da navegação no Google Modo IA e da captura das informações exibidas na página.

## Alterações validadas

- sessão persistente de Chrome/Edge;
- page load strategy `eager`;
- captura semântica do bloco da resposta;
- espera adaptativa por estabilidade;
- rolagem para conteúdo lazy-loaded;
- parser de títulos com emojis e Markdown;
- alternativas no formato `Alternativa A:`;
- métricas exibidas na interface;
- encerramento manual da sessão Google.

## Testes

- 45 testes automatizados concluídos com sucesso;
- compilação de `app.py` e de todos os módulos de `core`: aprovada;
- diagnóstico integrado: concluído sem falhas locais;
- regressão de importação, Telegram, análise apurada, Markdown e banco SQLite: aprovada.

## Limitação

A navegação real depende da disponibilidade do Modo IA para a conta, da conexão, da versão do Chrome/Edge e de eventuais verificações do Google. O programa não tenta contornar CAPTCHA.
