# Validação — QuestFlow Studio 6.10.3 / Mobile 0.7.3

## Escopo da correção incremental
- Removido `backdrop-filter` do backdrop de tela inteira dos modais e desativado o blur da topbar enquanto o modal está aberto.
- Substituída a animação com composição mais pesada por `opacity + translateY`, sem `scale()`.
- Adicionada instrumentação de `pageshow`, `visibilitychange`, `longtask` e ciclo de abertura/fechamento de modais.
- Observabilidade de Retrieval passou a ser **read-only ao abrir**: lê o último snapshot e o estado atual do índice sem executar benchmark nem registrar novo snapshot.
- Quality Gates passaram a ser **read-only ao abrir**: usam o último gate persistido/cache e só executam avaliação com a ação explícita **Reavaliar gates**.
- `0 Questões Ouro` não é mais representado como qualidade `0.0`: Score/Recall/Grounding são `null` e a UI mostra **Não avaliado**.
- Cabeçalhos e metadados de Retrieval usam release/engine atuais em vez de versões antigas hardcoded.
- Informações técnicas/histórico ficam em divulgação progressiva; ações administrativas ficam em **Modo avançado**.
- Mobile permanece em **0.7.3**, sem mudança de contrato incompatível.

## Testes executados
- Suite ampla de Retrieval/Hardening/Web já executada durante a implementação: **95/95 aprovados**.
- Regressão Mobile executada durante a implementação: **40/40 aprovados**.
- Rodada final combinando Retrieval, Quality Gates, observabilidade, updater, web e Mobile: **76/76 aprovados**.
- `node --check web/app.js`: aprovado.
- Smoke test de release: aprovado; aplicação reporta **6.10.3**.
- SQLite `quick_check`: `ok`; **0** violações de foreign key.
- SBOM 6.10.3 gerada com integridade de lock válida.
- Matriz de compatibilidade: Python **3.13.5** disponível e smoke aprovado; versões 3.11/3.12/3.14 não estavam disponíveis neste ambiente para execução.
- Auditoria automática de vulnerabilidades: **não executada**, porque `pip-audit` não está instalado no ambiente de validação. O relatório registra explicitamente `unavailable`.

## Limite da validação do flicker
A alteração elimina no código as duas fontes de composição mais suspeitas (blur de tela inteira e blur simultâneo da topbar) e reduz a animação de camadas. Não é possível reproduzir exatamente o driver/GPU/Chrome do computador do usuário neste ambiente. Por isso, caso a barra azul continue no Windows real, os novos logs de UI permitem diferenciar repaint/long task de artefato nativo de navegador/GPU sem esconder o sintoma artificialmente.

## Segurança do pacote UPDATE
- `mobile/node_modules`: excluído.
- `.expo`: excluído.
- `data`: excluído.
- caches/builds temporários: excluídos.
- O banco existente permanece sob responsabilidade do atualizador seguro/backup/rollback.

## Simulação do atualizador seguro
- Atualização simulada **6.10.2 → 6.10.3** usando o `questflow_update_runner.py` presente na instalação 6.10.2.
- Resultado: `ok: true`; `rollback_performed: false`.
- Backup pré-atualização criado e `quick_check_ok: true`.
- Smoke pós-atualização: aprovado, versão reportada **6.10.3**.
- Teste de restauração do backup: aprovado para os bancos `mobile_control_plane.sqlite` e `questflow_questions.sqlite`.
- SHA-256 do banco principal antes e depois da atualização: **idêntico**, confirmando preservação dos dados na simulação.
