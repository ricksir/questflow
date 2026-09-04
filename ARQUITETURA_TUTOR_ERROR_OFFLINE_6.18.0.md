# QuestFlow 6.18.0 — Revisão de Erros e Reserva Offline Estrita

## Objetivo

A release 6.18.0 fecha três lacunas do fluxo de estudo sem criar um Learning Engine paralelo no Mobile:

1. transformar a antiga lista de erros recentes do Tutor IA em uma fila de trabalho pedagógica;
2. garantir que a Reserva Offline não reapresente questão já respondida antes do vencimento definido pelo Studio;
3. tornar o comportamento offline do Mobile inequivocamente local e melhorar a eliminação visual de alternativas.

## 1. Revisão de Erros com o Tutor IA

O workspace do Tutor passa a separar dois estados:

- **Revisão de Erros com o Tutor IA**: último erro da questão é posterior à última orientação Tutor aprovada;
- **Erros Tratados**: existe orientação Tutor aprovada em data igual ou posterior ao último erro da questão.

A aprovação é, portanto, um evento de workflow. Ao aprovar a orientação, a questão sai da fila pendente e entra em Erros Tratados. Se uma nova tentativa incorreta ocorrer depois, a questão volta automaticamente para Revisão de Erros com o Tutor IA.

A identidade da questão continua sendo o UID interno, mas a interface exibe código e classificação humana.

## 2. Reserva Offline estritamente decidida pelo Studio

O Mobile não possui scheduler pedagógico próprio. A sequência continua sendo produzida pelo fluxo central:

`Learning Engine / Learner State -> StudyRepository -> StudyBatchService -> AdaptiveSessionOrchestrator -> Reserva Offline -> Mobile`

Depois que o scheduler central produz candidatos, a camada de preparação da Reserva Offline aplica uma regra adicional de segurança:

- questão **nunca respondida**: elegível;
- questão **já respondida**: elegível somente se `fsrs_due_at` (ou `due_at` legado) já venceu;
- questão respondida e ainda não vencida: excluída da reserva, mesmo que uma política de antecipação/manual pudesse selecioná-la em outro contexto.

Cada item da reserva recebe metadado explicativo `offline_eligibility`, com política `never_answered_or_studio_due_v1`.

A Reserva Offline continua sem gabarito ou índice da alternativa correta.

## 3. Resposta offline sem falsa sensação de conexão

Ao responder uma questão originada da Reserva Offline, o Mobile:

- grava imediatamente a tentativa no armazenamento local;
- não ativa o estado visual de “aguardando feedback” enquanto está offline;
- informa que não existe conexão em andamento;
- reconcilia a tentativa quando a sincronização com o Studio voltar;
- mantém o resultado posterior na área Respondidas offline.

Uma tentativa oportunista de sincronização pode ocorrer internamente, mas sua falha não deixa spinner permanente nem bloqueia a continuidade do estudo.

## 4. Eliminação de alternativa mais perceptível

O gesto horizontal de eliminação continua sendo apenas uma anotação local e não produz evento pedagógico. A alternativa eliminada passa a receber simultaneamente:

- texto riscado;
- cor de risco de alto contraste;
- borda e fundo diferenciados;
- badge da letra em estado eliminado;
- rótulo explícito `✕ ALTERNATIVA ELIMINADA`.

Tocar novamente na alternativa continua permitindo desfazer/selecionar conforme o fluxo do Mobile.

## 5. Compatibilidade

- Studio: 6.18.0
- Mobile: 0.13.0
- Migração destrutiva de banco: nenhuma
- Cloud Sync: contrato preservado
- FSRS/KT/IRT/Learner Model: não reimplementados no Mobile
- Mobile 0.13.0 exige atualização das fontes; para APK Preview com bundle embutido é necessário gerar/instalar nova build 0.13.0.
