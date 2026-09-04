# Validação técnica — QuestFlow Studio 6.6.8

## Escopo
Release de infraestrutura **Runtime Watchdog & Self-Healing**, com supervisor central, concorrência assíncrona controlada, rate limiting local, controle de histórico e relatório de compatibilidade.

## Watchdog central
O supervisor é infraestrutura transversal e **não cria um sétimo motor**. São supervisionados:

- servidor HTTP local / heartbeat da interface;
- SQLite local, latência, WAL, `quick_check` periódico e versões de schema;
- runtime assíncrono;
- fila de tarefas em background;
- os seis motores QuestFlow;
- Cloud Sync / Turso;
- Telegram + agendador, quando configurados e iniciados.

Estados: `healthy`, `offline`, `degraded`, `suspect`, `recovering`, `failed`, `disabled`, `initializing`.

A autorrecuperação é limitada por janela/cooldown. SQLite e servidor local não possuem reinicialização automática destrutiva. Falta de internet é **offline normal** e não dispara recuperação do banco.

## Concorrência e event loop
- Um event loop assíncrono de background é dedicado a I/O concorrente.
- Concorrência é limitada por semáforo configurável.
- IA, monitor de atualizações e envios de I/O podem usar o runtime assíncrono.
- OCR/carga de CPU permanece no pool tradicional, evitando misturar perfis de carga.
- Heartbeat do event loop permite detectar loop vivo porém travado.

## Rate limiting
Token bucket thread-safe local para integrações externas críticas:

- OpenAI;
- Gemini;
- Anthropic;
- Turso;
- monitor de atualizações.

Os limites de IA e Turso são configuráveis em **Configurações > Watchdog central e autorrecuperação**. Os mecanismos de retry/backoff dos provedores permanecem ativos.

## Controle de histórico
- histórico de tarefas em memória limitado e configurável;
- journal do Watchdog em JSONL com rotação por tamanho;
- `startup_performance.log` com rotação automática;
- histórico recente do supervisor visível na interface;
- eventos de recuperação registram serviço, estado, erro e ação tomada;
- não são gravadas API keys no journal do Watchdog.

## Modernização e compatibilidade
A interface mostra relatório do runtime com:

- versão única do QuestFlow;
- Python e matriz validada **3.11–3.13**;
- SQLite e mínimo funcional **3.24.0**;
- versões dos schemas aplicados no banco;
- arquitetura/bitness do sistema;
- versões detectadas de dependências opcionais relevantes;
- avisos de compatibilidade sem impedir o modo local quando a degradação é segura.

## Banco
Não há nova migração de dados nesta release. Permanecem:

- `question_bank`: v8
- `study`: v10
- `ai_governance`: v4

O journal do Watchdog fica fora do SQLite principal.

## Regressão
A suíte foi executada em três partições, com os mesmos testes do discovery completo:

- 111 testes — aprovados;
- 131 testes — aprovados;
- 130 testes — aprovados.

**Total: 372/372 testes aprovados.**

Validações adicionais:

- testes específicos do Watchdog/Self-Healing: aprovados;
- Cloud Sync e diagnóstico de sincronização: aprovados;
- runtime assíncrono e shutdown imediato sem coroutine órfã: aprovados;
- API HTTP local do Watchdog: aprovada;
- estado offline sem autorrecuperação indevida: aprovado;
- limite de reinicializações: aprovado;
- `node --check web/app.js`: aprovado;
- compilação dos módulos Python: aprovada.

Os `ResourceWarning` de conexões SQLite legadas observados em alguns testes antigos não produziram falhas; não houve `RuntimeWarning` do novo event loop na regressão final.
