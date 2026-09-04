# Arquitetura — Correções separadas e resumo offline — 6.18.1

## Objetivo

Separar visualmente e conceitualmente pendências editoriais de conteúdos ainda não estudados, mantendo a marcação pedagógica fora das métricas de erro, e corrigir o resumo de sessões offline no Mobile.

## Studio

A rota interna continua `corrections` por compatibilidade, mas a superfície passa a se chamar **Correções e Matérias não Estudadas**. A API `list_corrections` preserva `items` e `summary` e passa a expor também `corrections` e `not_studied`, permitindo consumidores novos tratarem as duas filas sem quebrar integrações antigas.

A interface possui duas áreas independentes:

1. **Correções** — somente `item_type != not_studied`.
2. **Matérias ainda não estudadas** — somente `item_type == not_studied`.

Ações de correção continuam usando `StudyRepository`; ações de conteúdo não estudado continuam usando `MobileFoundationService`. Não há migração de banco.

## Mobile

O Mobile 0.13.1 mantém a mesma Reserva Offline controlada pelo Studio. O resumo de sessão usa:

- `answered`: respostas registradas;
- `correct`/`wrong`: somente resultados já julgados;
- `pending_results`: respostas offline ainda aguardando correção pelo Studio.

Quando existem respostas, mas nenhum resultado corrigido, a interface não exibe mais apenas `—`. Ela mostra o número de questões respondidas e um indicador **Aguardando correção**, deixando explícito que o percentual será calculado após a sincronização.

## Limites arquiteturais preservados

- Learning Engine permanece somente no Studio.
- FSRS/KT/IRT não são executados no Mobile.
- Matéria não estudada não vira erro.
- O Mobile não calcula gabarito offline.
- Cloud Sync não foi alterado.
- Nenhuma migração destrutiva.
