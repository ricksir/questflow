# Validação QuestFlow Studio 5.4.3

## Escopo

A versão 5.4.3 adiciona encerramento protegido e verificação cruzada do banco local com o Turso.

## Encerramento protegido

Foram testados dois caminhos independentes:

- botão **Fechar QuestFlow com segurança**;
- fechamento direto da janela (X/Alt+F4), detectado por perda persistente do heartbeat.

Nos dois caminhos, o runtime chama `api.shutdown(...)` **antes** de terminar o processo do Chrome. A rotina interrompe o fluxo Telegram, solicita flush do Cloud Sync, cancela trabalhos ainda não iniciados, executa `wal_checkpoint(FULL)`, `quick_check`, `PRAGMA optimize` e tenta `wal_checkpoint(TRUNCATE)`. O relatório é gravado em `data/last_clean_shutdown.json`.

Se a sincronização final falhar por falta de Internet, a outbox SQLite continua durável e é processada na próxima abertura.

## Saúde do banco e Turso

A Visão Geral consulta de forma assíncrona:

- `PRAGMA quick_check` local;
- `PRAGMA foreign_key_check` local;
- quantidade física de `questions` no SQLite;
- quantidade lógica corrente de questões no log remoto do Turso (último evento por `row_key`, ignorando deletes);
- geração local/remota;
- sequência remota máxima versus sequência já aplicada localmente;
- pendências, conflitos e último erro.

O painel só afirma **totalmente sincronizado** quando todos os critérios coincidem.

## Testes

- suíte completa: **189 testes aprovados**;
- testes novos 5.4.3: sincronização com contagens iguais, divergência de contagem, relatório de shutdown limpo, solicitação idempotente, botão de fechamento, fechamento direto por X e presença do painel na interface;
- `node --check web/app.js`: aprovado;
- compilação Python dos módulos modificados: aprovada;
- diagnóstico local: concluído sem falhas locais;
- SQLite do pacote: `PRAGMA quick_check = ok`.

A validação real contra a conta Turso do usuário deve ser feita na instalação em uso, pois token/URL privados não são incorporados ao ZIP distribuído.
