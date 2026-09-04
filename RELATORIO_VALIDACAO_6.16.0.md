# Relatório de Validação — QuestFlow Studio 6.16.0 / Mobile 0.11.0

Gerado em: 2026-08-20T19:06:07Z

## Escopo

Atualização incremental para:

- eliminação visual de alternativas por gesto horizontal no Mobile;
- confirmação e preservação do boundary pedagógico: o Studio continua sendo a autoridade que decide a sequência de estudo;
- Reserva Offline planejada pelo Learning Engine do Studio e persistida no Mobile para uso sem internet e com o Studio fechado;
- fila local de respostas offline para sincronização posterior.

## Resultado arquitetural

O Mobile **não recebeu um Learning Engine paralelo**. A seleção online permanece no fluxo central `StudyRepository -> StudyBatchService -> AdaptiveSessionOrchestrator -> Mobile`. A Reserva Offline é um snapshot ordenado pelo Studio no momento da sincronização, após a ingestão dos eventos pendentes do aluno. Offline, o Mobile apenas consome essa ordem e registra evidências para a próxima sincronização.

O gabarito não é enviado na Reserva Offline. Assim, uma resposta feita totalmente offline pode avançar para a próxima questão, mas a correção e a atualização de FSRS/KT/IRT/learner model permanecem centralizadas e são consolidadas quando a sincronização volta a ocorrer.

## Validações executadas

- Testes direcionados de offline pack, Adaptive Session Orchestrator, runtime adaptativo, Study Batch, boundary Mobile/Studio, sessão Mobile e Cloud Bridge: **31 aprovados, 0 falhas**.
- Lote anterior de testes de versão/estáticos/regressão da release: **104 aprovados, 0 falhas**.
- Mobile `npm run typecheck`: **aprovado**.
- Mobile `npm run test:core`: **aprovado**.
- Expo Android export/bundle: **aprovado**, 1.363 módulos empacotados no teste de bundle.
- Studio smoke test: **aprovado**; aplicação 6.16.0.
- SQLite principal: `PRAGMA quick_check = ok`; foreign key violations = **0**.
- Banco usado na validação: **1.292 questões** e **39 registros de studied_scope**.
- Python 3.13.5: smoke **aprovado**. Python 3.11/3.12/3.14 não estavam disponíveis no ambiente e não foram marcados como aprovados.
- SBOM CycloneDX: gerado.
- Auditoria `pip-audit`: não executada por indisponibilidade do módulo no ambiente (`status=unavailable`), registrada sem falsa aprovação.

## Testes não concluídos / não executados

- A suíte pytest monolítica completa não terminou dentro do limite do ambiente; chegou a aproximadamente 24% sem falhas antes do timeout/processos lentos já conhecidos. Por isso ela **não é declarada como integralmente aprovada**.
- O gesto horizontal não foi testado fisicamente em um aparelho Android/iPhone neste ambiente; houve validação TypeScript e bundle React Native.
- Um APK Preview/Production assinado via EAS não foi produzido neste ambiente, pois isso depende do serviço externo EAS/credenciais e acesso à internet.

## Migrações e impacto no banco

- **SQLite principal do QuestFlow Studio:** nenhuma migração destrutiva e nenhuma alteração de schema exigida para esta funcionalidade.
- **SQLite do Mobile:** criação idempotente da tabela `qf_offline_study_pack` e do índice `idx_qf_offline_pack_question` na abertura do banco Mobile.
- Respostas offline continuam no outbox/local attempts existente e são processadas pelo Studio na sincronização.
- Nenhum FSRS, KT, IRT, mastery, learner model, XP ou histórico é recalculado autonomamente pelo Mobile.

## Impacto no Cloud Sync

O endpoint Mobile `/api/v1/mobile/sync` foi estendido. Primeiro o Studio ingere os eventos pendentes; depois gera/puxa o estado e, por fim, devolve uma nova Reserva Offline. Isso evita gerar a próxima sequência com um learner state anterior às respostas recém-sincronizadas. A mudança não requer ressincronizar integralmente o Learner State no Turso.

## Impacto no Mobile

Versão alterada de **0.10.1 para 0.11.0**, pois houve mudança real de código Mobile.

- Swipe horizontal à esquerda ou direita risca/desrisca uma alternativa; o gesto é somente uma ajuda visual e **não vira evidência pedagógica**.
- Tocar em uma alternativa riscada a seleciona e remove o risco.
- A Reserva Offline é exibida na preparação da sessão e mantém a ordem decidida pelo Studio.
- Ao responder offline, o usuário pode continuar para a próxima questão sem aguardar o gabarito; a correção fica pendente até a próxima sincronização.

## Limitação operacional importante

Para iniciar o aplicativo do zero sem internet, sem Studio e sem Metro, é necessário usar uma build **Expo Preview/Production com o bundle JavaScript embarcado**. Um Expo Dev Client pode depender do Metro em uma abertura fria. O pacote inclui `GERAR_APK_MOBILE_0.11.0_EAS.bat` para solicitar uma build Preview via EAS quando houver internet e credenciais configuradas.

Depois de instalada uma build embarcada, basta sincronizar ao menos uma vez com o Studio para abastecer a Reserva Offline; então as questões reservadas podem ser respondidas sem internet e com o Studio fechado.
