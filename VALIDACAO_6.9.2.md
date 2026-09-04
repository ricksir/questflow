# Validação — QuestFlow Studio 6.9.2 + Mobile 0.1.1

## Cenários novos

- rota ativa `192.168.15.131` é priorizada sobre endereço secundário/antigo `192.168.128.84`;
- troca de rede é recalculada em chamadas sucessivas, sem cache do IPv4 da inicialização;
- loopback e link-local não são publicados ao Mobile;
- QR aceita múltiplos `server=` em ordem de preferência;
- parser Mobile preserva servidor preferencial e candidatos alternativos;
- gerador de descoberta Mobile cria candidatos na /24 atual e não testa o próprio IP;
- teste de temporização legado de 1 hora aberta / 42 segundos ativos continua aprovado.

## Segurança preservada

- QR continua sem credencial administrativa do banco;
- pareamento continua temporário e de uso único;
- redescoberta pós-pareamento só aceita um endpoint que também aceite o Bearer token da sessão existente;
- outbox offline não é descartada durante troca de rede.

## Execução nesta montagem

- 81 testes Python direcionados: **OK**.
- `python -m compileall`: **OK**.
- `node --check web/app.js`: **OK**.
- testes puros TypeScript do Mobile: **OK**.
- transpile sintático de todos os arquivos TS/TSX: **OK**.
- `release_tools.py lock-check`: **OK**.
- `release_tools.py smoke`: **OK**, versão 6.9.2, SQLite `quick_check=ok`, zero violações de foreign key.
- `pip-audit`: indisponível no ambiente; registrado em `AUDITORIA_VULNERABILIDADES_6.9.2.json` e não tratado como auditoria concluída.
