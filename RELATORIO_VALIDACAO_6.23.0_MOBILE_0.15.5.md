# Validação — QuestFlow Studio 6.23.0 + Mobile 0.15.5

## Escopo

- Studio `6.23.0`.
- Mobile compatível `0.15.5`, sem alteração de APK.
- Migração SQLite somente aditiva.
- Pacote para QuestFlow Manager com `data`, ambientes e runtime excluídos.

## Resultados

- Compilação Python e JavaScript: aprovada.
- Compilação TypeScript do Studio: aprovada.
- Testes de arquitetura, Studio v1, APIdasQuestões e regressão WebApi: 15 aprovados.
- Testes Python de integração Mobile: 14 aprovados.
- Typecheck e testes core do Mobile: aprovados.
- ZIP: 985 entradas, zero caminhos inseguros e zero arquivos transitórios/protegidos.
- Smoke test do conteúdo exato do ZIP: aprovado como `6.23.0`.
- Aplicação simulada 6.22.16 → 6.23.0: aprovada, sem rollback.
- Backup e teste de restauração na simulação: aprovados.
- SQLite da instalação simulada: preservado byte a byte; `quick_check` aprovado.
- Mobile incluído no ZIP: não; a instalação mantém o Mobile 0.15.5 atual.

## Pacote

- Arquivo: `QuestFlow_Studio_6.23.0_UPDATE.zip`
- Tamanho: `3.057.037 bytes`
- SHA-256: `A8CBA948C42043D8DBB7A8E34BD0FF5CC66430CE804D43FF8261F8B230AAE730`
