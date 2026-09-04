# Cloud Sync Safe Activation — QuestFlow 6.14.1

## Objetivo

A 6.14.1 habilita o Cloud Sync de forma progressiva e protegida. A primeira escrita no Turso deixa de ser consequência de um simples `ON`: ela só ocorre após um preflight somente-leitura, comparação local/remota, dry-run da fila, verificação de conflitos e backup local validado.

O Mobile permanece **0.10.0 / Study Only**. Toda configuração, saúde, diagnóstico e governança do Cloud Sync continuam exclusivamente no QuestFlow Studio.

## Fronteira arquitetural

```text
Mobile 0.10.0
    │ eventos/respostas de estudo
    ▼
QuestFlow Core / Studio
    │
    ├─ Learning Engine / FSRS / KT / IRT
    │
    └─ CloudSyncEngine
         │
         ├─ fila local persistente (outbox)
         ├─ preflight somente-leitura
         ├─ backup SQLite validado
         ├─ idempotência por event_id
         ├─ checkpoints de ativação
         ├─ reconciliação / conflitos
         └─ retry exponencial
                    │
                    ▼
                  Turso
```

## Assistente de ativação segura

A primeira ativação percorre as seguintes etapas:

1. `PRAGMA quick_check(1)` e `foreign_key_check` no SQLite local;
2. validação de URL/token e teste de conexão com o Turso;
3. leitura do estado remoto sem escrita;
4. comparação das questões por ID e hash canônico, não apenas por contagem;
5. dry-run das alterações locais pendentes;
6. verificação de unicidade dos `event_id` e idempotência;
7. detecção antecipada de conflitos com eventos remotos ainda não vistos;
8. criação de backup SQLite antes da primeira escrita;
9. validação do backup por `quick_check`/FK e SHA-256;
10. primeira sincronização controlada;
11. ativação do sincronismo automático apenas quando fila e conflitos terminam em zero.

## Estados de ativação

A ativação é persistida em `qf_sync_runtime` por checkpoints, incluindo estado, horários, caminho/hash do backup e último erro.

Estados operacionais relevantes incluem:

- `activation_required`: credenciais/configuração podem existir, mas a primeira ativação segura ainda não foi concluída;
- `active`: primeira sincronização protegida concluída e sincronismo automático liberado;
- `failed`: tentativa falhou; o automático permanece desligado e a retomada é segura/idempotente.

## Comparação local x Turso

A comparação de questões usa uma representação canônica do payload para eliminar campos transitórios. O preflight informa:

- quantidade local/remota;
- IDs iguais;
- IDs somente locais;
- IDs somente remotos;
- IDs presentes nos dois lados com conteúdo divergente;
- igualdade de hashes canônicos;
- amostras pequenas das diferenças.

A simples igualdade de contagens não é considerada prova de consistência.

## Idempotência e recuperação

Os eventos remotos mantêm `event_id` único e usam gravação idempotente. Se houver falha depois de o Turso confirmar uma escrita, a repetição do mesmo evento não deve duplicar a operação.

O serviço mantém fila local durável e checkpoint da ativação. Em falhas transitórias, o retry usa backoff exponencial configurável, com base padrão de 5 s e teto padrão de 300 s.

## Conflitos

O preflight verifica eventos remotos ainda não vistos e pode prever disputa sobre a mesma entidade/linha antes da primeira escrita. Conflitos previstos bloqueiam a ativação automática até resolução explícita.

Quando os bancos local e remoto diferem sem conflito bloqueante, a UI exige confirmação humana da estratégia recomendada (`merge` ou origem local quando a nuvem está vazia).

## Dados canônicos e derivados

A fila classifica os grupos por domínio (`content`, `learner`, `integration`, `system`) e sinaliza estados derivados, como:

- `study_state`;
- `adaptive_model_state`;
- `topic_learning_state`;
- `lesson_learning_state`.

Essa separação prepara o QuestFlow para tratar eventos/respostas como evidência canônica e estados pedagógicos derivados como projeções reconstruíveis, reduzindo o risco de usar `last-write-wins` indiscriminadamente em FSRS/KT/modelo adaptativo.

## Studio

O Studio passa a mostrar **Ativação segura** no bloco de Cloud Sync. O sincronismo automático fica indisponível enquanto a ativação não for concluída.

O assistente apresenta saúde do SQLite, credenciais, conexão Turso, comparação por ID/hash, dry-run, conflitos, domínios dos dados e plano de backup antes da confirmação.

## Mobile

Nenhuma tela, endpoint ou configuração de Cloud Sync é acrescentada ao Mobile. A versão permanece 0.10.0. O aplicativo continua responsável apenas pela experiência de estudo e devolução de eventos ao QuestFlow.
