# Validação — QuestFlow Studio 6.9.6 + Mobile 0.3

Release: **6.9.6**  
Mobile: **0.3.0 — Cloud Bridge**  
Protocolos: `questflow.mobile.v1` + `questflow.mobile.cloud.v1`

## Resultado

- Suíte Python particionada: **484/484 testes aprovados**.
- `python -m compileall`: aprovado para núcleo e pontos de entrada alterados.
- `node --check web/app.js`: aprovado.
- `npm run test:core` do Mobile: aprovado, incluindo proteção do tempo ativo e parsing do QR com Cloud Bridge.
- Verificação sintática adicional: **10 arquivos TypeScript/TSX alterados** aprovados via TypeScript `transpileModule`.
- `requirements.lock`: íntegro, SHA-256 validado.
- Smoke test do pacote: aprovado; runtime reporta **6.9.6**.
- SQLite principal: `integrity_check = ok`, sem violações de foreign key no smoke test.
- Matriz local: Python **3.13** disponível e aprovado; 3.11/3.12 não instalados neste ambiente; 3.14 permanece experimental.
- SBOM CycloneDX 1.5: `SBOM_6.9.6.cdx.json` gerado.
- Auditoria automatizada de vulnerabilidades: relatório gerado, porém `pip-audit` não está instalado neste ambiente; o resultado está explicitamente marcado como `unavailable`, sem alegação de auditoria externa concluída.

## Cenário ponta a ponta validado do Cloud Bridge

1. Studio publica projeções Mobile e um pacote limitado de questões no Gateway.
2. Mobile autentica no Gateway com o mesmo token já pareado; o Gateway armazena apenas o hash da sessão.
3. Mobile recebe `bootstrap`, `today`, `progress` e questões sem exposição do banco interno.
4. Uma resposta enviada ao Gateway recebe feedback provisório do pacote seguro.
5. Antes do Studio drenar a fila, a tentativa ainda não altera a métrica definitiva no banco do QuestFlow.
6. O Studio drena o evento, aplica a mesma esteira idempotente/imutável do Mobile e confirma a métrica definitiva.
7. O evento é reconhecido no Gateway e deixa a fila pendente.
8. Também foi validado o caso de desconectar o aparelho depois de responder e antes do Studio drenar: o evento autenticado é aplicado antes da desconexão, evitando perda da resposta.

## Limites operacionais intencionais

- O primeiro pareamento continua sendo feito pelo Studio.
- Para uso real por 4G/5G ou outra rede, `mobile_cloud_gateway.py` precisa ser hospedado em um servidor/VPS acessível por **HTTPS** e o Studio precisa receber a URL e a chave administrativa desse Gateway.
- O Mobile não recebe credenciais do banco principal e não acessa diretamente tabelas internas do QuestFlow.
- O Cloud Bridge é transporte/projeção temporária; o Studio continua sendo a autoridade para Learning Engine, FSRS, métricas e curadoria.
