# Relatório de validação — QuestFlow Studio 6.23.2

## Resultado

- Correção de suspensão/hibernação implementada e aprovada.
- ZIP seguro gerado para atualização da versão 6.23.1 para 6.23.2.
- Mobile mantido em 0.15.6; não exige novo APK.
- Instalação real em `C:\Users\user\QuestFlow` permaneceu intocada na versão 6.23.1 durante a preparação.

## Comportamento corrigido

- Lacunas longas do relógio/agendador são reconhecidas como suspensão ou hibernação.
- A retomada exige um heartbeat realmente novo, inclusive quando o relógio monotônico do Windows pausa durante o sono.
- O Chrome recebe até 45 segundos para retomar naturalmente.
- Se a interface não retornar, somente a janela dedicada do Studio é relançada; backend, Mobile LAN, outbox e serviços internos permanecem ativos.
- Fechamento explícito e fechamento normal continuam executando checkpoint e encerramento seguro.
- Eventos de retomada são registrados em `data/runtime_lifecycle.jsonl`, com rotação em 1 MiB.
- O Manager oferece opções para ativar ou remover a inicialização automática do Studio com o Windows.

## Validações executadas

- Suíte integral `release_tools.py ci --full`: 136 módulos em quatro partições, zero falhas e zero módulos ignorados.
- Testes pytest complementares: 22 aprovados.
- Testes direcionados de suspensão, Chrome, fechamento seguro e manifesto: aprovados.
- Mobile 0.15.6: `npm run typecheck` e `npm run test:core` aprovados.
- Smoke test Python e verificação JavaScript aprovados.
- SBOM e matriz de compatibilidade 6.23.2 gerados; auditoria opcional ficou indisponível porque `pip-audit` não está instalado.

## Ensaio de atualização isolado

- Origem: 6.23.1.
- Destino: 6.23.2.
- Backup pré-atualização: aprovado.
- Teste de restauração: aprovado.
- SQLite `quick_check`: `ok`.
- Violações de chave estrangeira: 0.
- Rollback: não necessário.
- SHA-256 do banco antes e depois: `63E91D712CD9BEDD80B399EB728E743C4B4FBB57DE9F5757BA4DCC58CDC4419E`.

## Pacote

- Arquivo: `QuestFlow_Studio_6.23.2_UPDATE.zip`.
- Tamanho: 3.740.409 bytes.
- Entradas: 1.157, todas sob a raiz `QuestFlow/`.
- Conteúdo `data/`: ausente, como exigido.
- SHA-256: `92685AC2F94DC71D8866569BA8A567F6EFA704CB181C95235D4BD5F9F9AC4997`.
