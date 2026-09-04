# Validação — QuestFlow Studio 6.22.16 + Mobile 0.15.5

## Resultado

- Studio: `6.22.16`.
- Mobile: `0.15.5`, Android build `20`, pacote `br.questflow.mobile`.
- EAS build: `FINISHED`, fingerprint `b786babf48bd1d117a878610e6a7f1e38c153cb1`.
- Banco: nenhuma migração e nenhum dado persistente incluído no pacote.

## Correções verificadas

- O Studio não contém mais textos ativos `Mobile 0.14.0` ou `build 0.14`.
- Os scripts do Studio usam cache-busting `6.22.16` para impedir JavaScript antigo no WebView.
- “Resultado por resposta” permite quebra responsiva e exibe a variação como `p.p. desde o início`.
- Ações da questão, nesta ordem: Continuar; Pular Questão; Assunto ainda não Estudado; CORRIGIR QUESTÃO.
- O envio da resposta usa uma requisição leve que registra eventos e devolve o feedback no mesmo retorno.
- Reserva offline e bootstrap continuam atualizados pelo sincronismo completo em segundo plano.

## Testes executados

- TypeScript: `tsc --noEmit` — aprovado.
- JavaScript: `node --check` em `app.js`, `questflow621.js` e `questflow622.js` — aprovado.
- Python: compilação de `core/mobile_foundation.py` — aprovada.
- Testes focados estáticos: 8 — aprovados.
- Testes de cockpit Mobile/Studio: 3 — aprovados.
- Estrutura do ZIP: 1.111 entradas; 0 entradas proibidas (`data`, `.git`, `node_modules`, `.expo`, `dist`, caches).
- APK: arquivo ZIP Android íntegro; metadados de versão/build confirmados pelo EAS.

## Observação de desempenho

O caminho crítico deixou de executar sincronização completa + bootstrap + consulta separada de feedback. A resposta agora utiliza uma única ida leve ao Studio, com limite de 6 segundos; a atualização completa ocorre depois que o resultado já está visível.
