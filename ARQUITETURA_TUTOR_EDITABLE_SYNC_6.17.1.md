# Arquitetura — Tutor IA editável e sincronizado com a questão — QuestFlow 6.17.1

## Objetivo

Corrigir dois problemas do Tutor IA sem destruir a trilha de auditoria:

1. o rascunho gerado pela IA precisa poder ser revisado e editado pelo usuário;
2. uma questão alterada em **Revisar banco** não pode continuar usando silenciosamente uma orientação produzida sobre uma versão anterior.

## Regra de governança

O texto original produzido pela IA permanece imutável em `qf_ai_interactions.response_text`.
A edição humana é armazenada separadamente em `edited_response_text` e cada salvamento gera uma revisão em `qf_ai_response_revisions`.

```text
IA gera orientação
      ↓
response_text (original imutável)
      ↓
usuário revisa
      ↓
edited_response_text (versão de trabalho)
      ↓
qf_ai_response_revisions (histórico)
```

Salvar uma edição humana:

- mantém o original da IA;
- cria uma revisão auditável;
- retorna a interação para `rascunho`;
- executa novamente a avaliação independente sobre o texto revisado.

## Sincronização com Revisar banco

Toda nova interação do Tutor registra um snapshot semântico da questão e seu SHA-256. O snapshot inclui código, matéria, assunto, aula, enunciado, alternativas, gabarito, explicação e código da fonte.

Ao reabrir o Tutor, o snapshot é comparado com a versão atual da questão.

```text
snapshot usado pela orientação
             ↓
        SHA-256 armazenado
             ↕ comparação
        SHA-256 atual
             ↓
igual       → orientação atual
alterado    → orientação desatualizada
```

Quando a questão foi alterada:

- o Workspace mostra imediatamente a questão atual;
- a orientação anterior continua preservada como histórico;
- aparece o aviso **Questão alterada em Revisar banco**;
- a aprovação do rascunho anterior é bloqueada também no backend;
- o usuário pode clicar em **Gerar novamente com a questão atual**.

A regeneração cria uma nova interação. A anterior não é apagada nem reescrita.

## Compatibilidade com orientações antigas

Interações criadas antes da 6.17.1 não possuíam snapshot da questão. A versão candidata inicialmente usava `questions.updated_at > interaction.created_at` como aproximação, mas isso é inseguro: sincronizações, reindexações e outras manutenções podem atualizar `updated_at` sem alterar o conteúdo pedagógico da questão.

A release final usa a migração `ai_governance` versão 6:

- orientações legadas sem hash recebem, uma única vez, o **hash do conteúdo pedagógico atual no momento da atualização**;
- esse registro recebe origem `legacy_upgrade_baseline_6171`;
- alterações técnicas anteriores à atualização não geram falso aviso de “questão alterada”;
- qualquer alteração pedagógica posterior ao baseline muda o hash e torna a orientação antiga desatualizada corretamente;
- a Auditoria informa que esse baseline legado não é uma reconstrução exata da questão existente no dia da geração original.

Essa estratégia é conservadora: não inventa um histórico que o banco antigo não possuía e, ao mesmo tempo, passa a detectar mudanças reais de conteúdo a partir da atualização.

## Migrações de banco

Migração `ai_governance` versão 5:

- `edited_response_text`;
- `edited_at`;
- `edit_note`;
- `question_snapshot_sha256`;
- `question_snapshot_json`;
- `question_updated_at`;
- tabela `qf_ai_response_revisions`.

Migração `ai_governance` versão 6:

- `question_snapshot_origin`;
- `question_snapshot_captured_at`;
- backfill idempotente dos hashes/snapshots das orientações legadas.

Não há remoção de tabela, coluna ou dado existente.

## Fronteiras preservadas

Não houve alteração no Learning Engine, FSRS, Knowledge Tracing, IRT, Adaptive Session Orchestrator, Course Catalog, Reserva Offline ou QuestFlow Mobile.

As novas tabelas/campos de auditoria do Tutor permanecem locais e não foram adicionados ao conjunto de tabelas do Cloud Sync.
