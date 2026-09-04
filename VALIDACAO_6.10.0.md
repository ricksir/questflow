# Validação — QuestFlow Studio 6.10.0 / Mobile 0.7.0

## Escopo

- Study Session configurável no Mobile.
- Filtros de lote por revisão, histórico de erro e matéria.
- Persistência e retomada de sessão no SQLite local do aparelho.
- Resumo final da sessão.
- Compatibilidade com Study Triage, cronômetro ativo, safe area Android, Professional UX, Manager e Recovery Guard.

## Resultado

- 495/495 testes Python aprovados, executados em sete partições para respeitar o limite operacional do ambiente.
- `npm run test:core` aprovado no Mobile 0.7.0, incluindo cronômetro, formatação de duração e restauração lógica de sessão.
- Testes novos de `question_batch` aprovados para `recommended`, `review`, `errors` e `subject`.
- Transpilação sintática de todos os arquivos `.ts`/`.tsx` aprovada com TypeScript `transpileModule`.
- `release_tools.py smoke` aprovado: runtime 6.10.0 e SQLite da release íntegro, sem violações de foreign key.
- `requirements.lock` íntegro e SHA-256 conferido.
- Atualização segura 6.9.9 → 6.10.0 simulada em instalação temporária: backup, preservação de `data`, smoke e restore-test aprovados; rollback não foi necessário.
- SBOM CycloneDX 1.5 gerado em `SBOM_6.10.0.cdx.json`.
- Matriz de compatibilidade gerada; Python 3.13 disponível no ambiente e smoke aprovado. 3.11/3.12 não estavam disponíveis neste runtime; 3.14 permanece experimental pela política do projeto.
- `pip-audit` não estava instalado no ambiente; o relatório registra `status=unavailable` em vez de marcar auditoria como aprovada.

## Observações

A tentativa de `npm run typecheck` integral no pacote extraído não é um gate válido neste ambiente porque o ZIP de release não inclui `node_modules`/tipagens Expo. Por isso, a validação da camada Mobile foi feita com `test:core` e transpilação sintática TS/TSX. No computador de desenvolvimento, após o Manager preparar as dependências do Mobile, o typecheck integral pode ser executado normalmente.
