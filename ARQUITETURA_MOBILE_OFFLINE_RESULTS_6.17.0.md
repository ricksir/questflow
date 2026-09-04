# Arquitetura — resultados de respostas offline — QuestFlow 6.17.0 / Mobile 0.12.0

## Objetivo

Permitir que o aluno consulte, depois da sincronização, o resultado de **todas** as questões respondidas offline, mesmo quando a questão já não está aberta no aplicativo.

## Fronteira pedagógica preservada

```text
QuestFlow Studio
Learning Engine / Learner State
        ↓
StudyRepository
        ↓
StudyBatchService
        ↓
AdaptiveSessionOrchestrator
        ↓
Reserva Offline (snapshot ordenado)
        ↓
QuestFlow Mobile
```

O Mobile não recebe um Learning Engine paralelo. Sem conexão ele apenas consome a Reserva Offline previamente ordenada pelo Studio e registra a resposta do aluno. O gabarito e a explicação não fazem parte da Reserva Offline.

## Ciclo de uma resposta offline

```text
Questão da Reserva Offline
        ↓
Aluno responde sem conexão
        ↓
Tentativa local: answered_offline = 1
        ↓
Evento permanece na outbox local
        ↓
Conexão/Studio volta
        ↓
Mobile envia eventos pendentes
        ↓
Studio processa a tentativa e atualiza Learner State
        ↓
Mobile percorre TODAS as tentativas offline sem feedback
        ↓
GET feedback(attempt_id)
        ↓
Resultado oficial salvo localmente
        ↓
Questões > Respondidas offline
```

## Persistência Mobile

A base local mantém a marcação `answered_offline`, a alternativa selecionada, metadados humanos da questão e o feedback oficial quando disponível. As consultas novas são:

- `listOfflineAttemptsAwaitingFeedback()` — fila de tentativas que precisam de resultado;
- `offlineAttemptHistoryInfo()` — totais resolvidos/aguardando;
- `listOfflineAttemptHistory()` — histórico para a interface.

Tentativas antigas da 0.11.x com alternativa marcada e feedback ausente podem ser classificadas como `legacy_pending_result` para reconciliação.

## Sincronização

A sincronização não considera somente a questão atualmente aberta. Depois do push da outbox, ela lista tentativas offline pendentes e consulta o feedback de cada tentativa. Falhas individuais não apagam a tentativa; ela permanece elegível para a próxima sincronização.

## Interface

A área **Respondidas offline** mostra:

- código/matéria/assunto;
- alternativa escolhida;
- estado `Aguardando`, `Correta` ou `Incorreta`;
- gabarito, quando devolvido pelo Studio;
- explicação oficial;
- comando para sincronizar novamente os resultados.

## “Refreshing” e botão de desenvolvimento

O Mobile 0.12.0 mantém Fast Refresh disponível em build de desenvolvimento, mas tenta ocultar o `DevLoadingView`/banner `Refreshing...`. O `expo-dev-client` é configurado com `toolsButton=false`, `showMenuAtLaunch=false` e `skipOnboarding=true`.

Como o botão do Dev Client é nativo, uma instalação antiga não pode removê-lo apenas trocando JavaScript. Para remoção definitiva é necessária uma nova build nativa 0.12.0. A build **Preview** é recomendada para uso diário e offline por não trazer chrome de desenvolvimento.

## Segurança e dados

- nenhum gabarito é colocado na Reserva Offline;
- nenhuma regra FSRS/KT/IRT é executada no Mobile;
- nenhuma migração destrutiva é feita no SQLite do Studio;
- respostas offline não são descartadas se a sincronização falhar;
- atualização de fontes Mobile preserva `node_modules`, `.expo`, `android` e `ios`.
