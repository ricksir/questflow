# Validação — QuestFlow Studio 5.4.0

## Resultado

- Suíte regressiva completa: **177 testes aprovados**.
- Suíte específica Turso/Cloud/Móvel: **20 testes aprovados**.
- `python -m compileall`: aprovado.
- `node --check web/app.js`: aprovado.
- `diagnostico.py`: concluído sem falhas locais.
- SQLite empacotado: `PRAGMA integrity_check = ok` e `PRAGMA quick_check = ok`.

## Matriz de cenários 5.4.0

| Cenário | Forma de teste | Resultado |
|---|---|---|
| PC A e PC B nunca ligados juntos | remoto Turso simulado compartilhado; A fecha logicamente antes de B sincronizar | aprovado |
| Uso sem Internet | remoto forçado offline; gravação local + outbox | aprovado |
| Internet volta depois | mesma fila é enviada posteriormente | aprovado |
| Queda após commit local | subprocesso termina por `os._exit()` após gravação | aprovado; banco íntegro e outbox persistente |
| Queda no meio da transação | subprocesso morre com `BEGIN IMMEDIATE` sem commit | aprovado; transação revertida e banco íntegro |
| Commit remoto sem ACK | remoto confirma evento e derruba a conexão antes da resposta | aprovado; retry idempotente, sem duplicação |
| Duas edições offline da mesma questão | A e B alteram a mesma chave | aprovado; conflito auditado, último push converge |
| Reset enquanto outro PC está offline | geração global + fila antiga no segundo PC | aprovado; progresso antigo descartado |
| Edição editorial anterior ao reset | segundo PC possui alteração de questão pendente | aprovado; edição editorial preservada e reclassificada para a geração atual |
| Novo PC instalado depois do reset | cliente vazio entra após geração 2 | aprovado; questões antigas reconstruídas e progresso da geração antiga ignorado |
| Banco temporariamente ausente | arquivo destacado do caminho | aprovado; status `database_unavailable` sem inventar sincronização |
| Banco ocupado/bloqueado | lock SQLite exclusivo | aprovado; status seguro e integridade preservada |
| Filas Telegram específicas do dispositivo | gravação em `flow_runtime`/filas operacionais | aprovado; não entram no Cloud Sync |
| Protocolo Turso SQL-over-HTTP | servidor HTTP de contrato, Bearer + `/v2/pipeline` | aprovado |
| Token Turso inválido | HTTP 401 de contrato | aprovado; classificado como falha de autenticação |
| Proxy direto/manual/auto e bypass local | suíte regressiva de Rede e Proxy 5.3.0 | aprovado |
| API móvel sem token | chamada `/api/call` na LAN sem header de sessão | aprovado; HTTP 401 |
| API móvel com token de sessão | mesma chamada com token aleatório correto | aprovado |
| Viewport móvel | verificação de `viewport` + breakpoints responsivos | aprovado |
| Regressão do QuestFlow | 177 testes de banco, Telegram, layout, importação, estudo e rede | aprovado |

## O que não foi falsamente declarado como teste real

O pacote de desenvolvimento **não contém credenciais de uma conta Turso real do usuário**. Por isso a montagem do ZIP não grava nem apaga dados em um banco Turso externo real. O protocolo e as falhas foram exercitados com um servidor de contrato local, e o QuestFlow contém o teste de aceitação real em **Configurações → Cloud Sync → Testar Turso** e no `diagnostico.py` quando URL/token estiverem configurados.

Também não foi aberto um firewall corporativo nem removido isolamento de clientes Wi‑Fi para o acesso móvel. O servidor LAN e a autenticação foram testados localmente; a alcançabilidade do celular depende da política da rede onde o programa for executado.

## Modelo de segurança

- Token Turso: DPAPI no Windows; não sincronizado e não retornado à interface.
- Proxy/senha: local ao dispositivo; não sincronizado.
- LAN móvel: desativada por padrão; token de sessão aleatório obrigatório.
- Loopback principal: continua isolado do proxy.
- Remote event ID: único/idempotente.
- Payload remoto: checksum SHA-256 antes de aplicar.
- Cloud Sync: não substitui backup local.
