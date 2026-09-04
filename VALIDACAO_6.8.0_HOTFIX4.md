# Validação técnica — QuestFlow Studio 6.8.0 Hotfix 4

## Escopo

Correção do retorno da explicação já renderizada no Google Modo IA para o editor do QuestFlow.

## Falha reproduzida

O Google exibia `Gabarito: CERTO` e uma seção `Explicação`, porém o backend recusava o conteúdo quando a resposta era obtida pela consulta de fallback do enunciado e não repetia código, banca ou ano.

## Alterações validadas

- ancoragem por consulta de código exato;
- ancoragem por consulta do enunciado com similaridade mínima controlada;
- captura DOM com prioridade para bloco compacto `Gabarito + Explicação/Justificativa/Resolução`;
- seleção de comentário substantivo verificado sem corte rígido de confiança;
- confiança preservada como indicador para revisão humana;
- proibição do texto integral da página como comentário;
- manutenção do gabarito local como fonte soberana.

## Resultado

- **423 / 423 testes automatizados aprovados**;
- partições: **111 + 97 + 110 + 105**;
- **24 / 24** testes focados do fluxo Google aprovados;
- **4 / 4** testes novos do Hotfix 4 aprovados;
- cenário Q105746 aprovado.
