# Validação técnica — QuestFlow Studio 6.8.0 Hotfix 3

## Escopo
Corrigir o falso negativo em que a justificativa aparecia no Google, mas era rejeitada pelo QuestFlow, e reorganizar as ações do editor.

## Mudanças de critério
- consulta por código exato ancora a resposta do Modo IA sem exigir eco de código/metadados;
- justificativa substantiva é preservada após limpeza mesmo com confiança inferior a 62%;
- confiança baixa gera aviso para revisão humana;
- texto geral da página continua proibido;
- sufixo inline após `Gabarito: X.` passa a ser capturado;
- limpeza final defensiva remove rótulos de interface antes do preenchimento.

## Interface
- bloco próprio de Pesquisa assistida;
- contador de caracteres separado;
- rodapé com Status da revisão + Ações;
- rótulos curtos em Curadoria;
- layout responsivo dos três botões.

## Resultado
- **419 / 419 testes automatizados aprovados**: 97 + 106 + 117 + 99;
- **20 / 20** testes Google 6.7.2–6.8.0;
- **4 / 4** testes novos Hotfix 3;
- **162 arquivos Python** compilados;
- `web/app.js` aprovado por `node --check`;
- banco: `quick_check = ok`;
- `foreign_key_check = 0`;
- diagnóstico Google: OK.

## Nota do ambiente
O contêiner de validação não possui Py-FSRS Optimizer; o diagnóstico geral acusa apenas essa dependência de ambiente. A pesquisa Google e o módulo principal 6.8.0 ficam OK.
