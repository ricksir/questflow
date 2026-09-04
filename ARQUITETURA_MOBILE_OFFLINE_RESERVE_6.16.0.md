# Arquitetura — Mobile Offline Reserve 6.16.0 / Mobile 0.11.0

## Princípio

O QuestFlow Mobile não possui Learning Engine paralelo. A autoridade pedagógica permanece no Studio.

```text
Learner State / FSRS / KT / IRT / Learner Model
                ↓
        StudyRepository
                ↓
        StudyBatchService
                ↓
 AdaptiveSessionOrchestrator (sessão online)
                ↓
             Mobile
```

## Reserva Offline

Na sincronização, o Mobile envia primeiro a outbox de eventos. O Studio aplica as respostas ao estado do aluno e, em seguida, gera uma nova `offline_study_pack` usando `StudyBatchService` e `StudyRepository.select_questions`.

```text
Mobile outbox
   ↓ sync
Studio aplica eventos
   ↓
Learning Engine / Learner State atualizado
   ↓
StudyBatchService seleciona próxima sequência
   ↓
offline_study_pack.v1 (sem gabarito)
   ↓
SQLite local do Mobile
```

Sem internet ou com o Studio fechado, o aplicativo apenas consome essa sequência previamente decidida. Não calcula FSRS, prioridade, KT, IRT ou ranking pedagógico no aparelho. As novas respostas ficam na outbox local até a próxima sincronização.

## Segurança do conteúdo

A Reserva Offline contém enunciado, alternativas e metadados de estudo necessários à apresentação. O gabarito e a explicação corretiva não são colocados no pack. Por isso, durante uso totalmente offline, o usuário pode continuar para a próxima questão sem ver o resultado; a correção acontece quando o Studio volta a receber os eventos.

## Gesto de eliminação

O risco em uma alternativa é um estado de interface (`eliminated`) da sessão local. Ele não é enviado ao Learning Engine, não altera estatísticas e não é tratado como resposta. Um swipe horizontal com limiar mínimo alterna o estado riscado; tocar na alternativa remove o risco e a seleciona.

## Persistência Mobile

Nova tabela local:

`qf_offline_study_pack(position, pack_id, question_id, revision, exam_project_id, generated_at, selection_policy, core_policy, consumed_at)`

As questões continuam armazenadas em `qf_question_cache`. Respostas offline continuam em `qf_outbox`/`qf_local_attempts`.

## Build realmente offline

O código funciona sem Studio e sem rede depois de sincronizar uma Reserva Offline, mas o aplicativo precisa estar instalado como build Preview/Production com bundle JavaScript embarcado. O Expo Dev Client em modo Metro é um ambiente de desenvolvimento e não deve ser usado como garantia de inicialização offline.
