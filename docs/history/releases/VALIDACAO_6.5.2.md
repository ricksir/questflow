# Validação técnica — QuestFlow Studio 6.5.2

## Motivo da release

Correção do caso em que o painel indicava alterações locais aguardando sincronização sem explicar quais eram e a outbox podia permanecer indefinidamente acima de zero.

## Regressão automatizada

A suíte foi executada em quatro partições devido ao limite de tempo do ambiente:

- Parte 1: 77/77
- Parte 2: 74/74
- Parte 3: 87/87
- Parte 4: 86/86

**Total: 324/324 testes aprovados.**

Também foram executados os testes históricos de Cloud Sync, fechamento seguro, integridade e estabilidade, incluindo:

- persistência de edição offline;
- crash após commit;
- retry idempotente;
- duas máquinas convergindo sem ficarem online ao mesmo tempo;
- conflitos auditados;
- reset de estudos preservando alteração editorial;
- banco temporariamente bloqueado/indisponível;
- shutdown sem bloqueio por sync em andamento.

## Testes novos 6.5.2

1. A fila identifica a alteração pendente até o nível da questão/código/matéria/aula.
2. Evento de tabela antiga não suportada é movido para `qf_sync_outbox_deadletter` e não permanece eternamente como pendente.
3. `sync_until_idle()` drena uma outbox válida.
4. Frontend e allowlist HTTP expõem o diagnóstico de pendências.

## Upgrade real 6.5.1 → 6.5.2

Foi criada uma base usando o `core/cloud_sync.py` original da 6.5.1, contendo:

- 1 alteração válida em `questions`;
- 1 evento legado de tabela removida;
- `qf_sync_outbox_deadletter` inexistente na base antiga.

Ao abrir a mesma base pela 6.5.2 e sincronizar:

- fila inicial: 2;
- evento válido enviado: 1;
- evento legado colocado em quarentena: 1;
- fila ativa final: 0;
- dead-letter final: 1;
- `PRAGMA quick_check`: **ok**.

## Integridade da arquitetura

A release não cria um novo motor. Permanecem os seis motores:

1. Banco Editorial
2. Learner Model
3. Learning Engine
4. Knowledge Engine
5. AI Engine
6. Evaluation & Governance Engine

A mudança fica na infraestrutura local-first/Turso e na apresentação de saúde do banco.
