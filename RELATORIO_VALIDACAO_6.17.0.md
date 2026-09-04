# Relatório de validação — QuestFlow Studio 6.17.0 / Mobile 0.12.0

## Escopo

Release focada em três pontos do Mobile: ocultação do chrome visual de desenvolvimento, remoção do botão flutuante em nova build nativa e histórico completo de resultados de questões respondidas offline.

## Testes aprovados antes do empacotamento

- **81 testes pytest direcionados:** aprovados, 0 falhas.
- Incluídos: resultados offline 6.17.0, Reserva Offline, Study Only, Mobile foundation/coach, Adaptive Session Orchestrator, batch adaptativo, Cloud Sync seguro, hardening, watchdog, atualizador Windows e Tutor IA.
- `npm run test:core`: aprovado.
- `npx tsc --noEmit`: aprovado.
- `npx expo export --platform android`: aprovado.
- Bundle Android: **1.369 módulos**.
- Smoke test Python 3.13.5: aprovado.
- SBOM CycloneDX: gerado.
- Auditoria `pip-audit`: não executada porque a ferramenta não está instalada no runtime; artefato registra `unavailable` em vez de aprovação falsa.

## Regras verificadas

- O Mobile não contém `StudyRepository` nem `AdaptiveSessionOrchestrator` e não implementa Learning Engine paralelo.
- Reserva Offline continua sem gabarito/`correct_index`.
- Sincronização usa `listOfflineAttemptsAwaitingFeedback()` e percorre todas as tentativas pendentes, não apenas a atual.
- Histórico persistente diferencia resolvidas e aguardando.
- Configuração Dev Client: `toolsButton=false`, `showMenuAtLaunch=false`, `skipOnboarding=true`.
- Fast Refresh não foi desativado; a alteração atua apenas no elemento visual de desenvolvimento.
- Atualizador Mobile protege `node_modules`, `.expo`, `android` e `ios`.

## Migrações

- Studio SQLite: nenhuma migração destrutiva nova para esta release.
- Mobile SQLite: evolução aditiva do estado local de tentativas offline; dados existentes são mantidos e tentativas antigas elegíveis podem entrar em reconciliação.

## Limitações conhecidas

- O botão flutuante já embutido em um Dev Client antigo só desaparece definitivamente após instalar uma nova build nativa 0.12.0.
- Não foi possível gerar/assinar uma build EAS neste ambiente porque depende de serviço externo e credenciais do projeto.
- O gesto/overlays não foram testados fisicamente no aparelho do usuário neste ambiente; TypeScript e bundle Android foram validados.
- Python 3.11, 3.12 e 3.14 não estão disponíveis neste runtime; a matriz os registra como não executados.
