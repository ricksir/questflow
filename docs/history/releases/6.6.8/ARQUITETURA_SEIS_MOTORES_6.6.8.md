# Arquitetura dos seis motores — QuestFlow Studio 6.6.8

A 6.6.8 mantém **exatamente seis motores**:

1. Banco Editorial
2. Learner Model
3. Learning Engine
4. Knowledge Engine
5. AI Engine
6. Evaluation & Governance Engine

## Onde entra o Watchdog

O **Runtime Watchdog & Self-Healing** é infraestrutura transversal do processo, não um motor pedagógico.

```text
                     RUNTIME WATCHDOG
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
   HTTP / UI            SQLite             Serviços
   heartbeat          quick_check       async runtime
   latência           WAL / schemas     Cloud Sync
                                        Telegram
                                        task runtime
                           │
                           ▼
                  seis motores QuestFlow
```

O supervisor observa a saúde, registra transições e pode reiniciar somente componentes que declaram uma rotina segura de recuperação.

## Regras de segurança

- SQLite é autoridade local dos dados e nunca é reiniciado pelo Watchdog.
- Falta de internet é estado `offline`, não falha crítica.
- Recuperação automática possui cooldown e número máximo de reinícios por janela.
- Desligamento solicitado pelo usuário não é desfeito pelo Watchdog.
- Nenhuma fila é apagada durante autorrecuperação.
- O journal do supervisor fica fora do banco principal.

## Runtime assíncrono

Um único event loop em thread dedicada atende tarefas de I/O que se beneficiam de concorrência. Um semáforo limita a quantidade de operações simultâneas. Cargas CPU/OCR permanecem no executor tradicional.

## Rate limiting

A camada de integrações externas usa token buckets locais para evitar rajadas acidentais. Retry/backoff continua separado do rate limiting.

## Compatibilidade

O painel de runtime apresenta Python, SQLite, schemas do banco, arquitetura do SO e dependências detectadas. Versões fora da matriz validada geram aviso quando ainda são tecnicamente suportáveis, em vez de bloquear silenciosamente o modo local.
