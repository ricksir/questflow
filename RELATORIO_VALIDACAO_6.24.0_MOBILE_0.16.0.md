# Relatório de validação — QuestFlow Studio 6.24.0 + Mobile 0.16.0

## Resultado funcional

- A prioridade da Visão geral foi transformada em uma área responsiva de cartões acionáveis, sem divergência entre a contagem e os itens apresentados.
- Até seis matérias ficam visíveis no Studio; os detalhes completos abrem diretamente pelo cartão escolhido.
- O Mobile mostra cinco matérias inicialmente e expande a lista sob demanda, evitando uma tela longa quando o catálogo crescer.
- A tela Hoje recebeu um roteiro de sessão baseado nos dados reais de revisão, recomendação e sincronização.
- Títulos, indicadores e ações do Progresso foram ajustados para telas estreitas e fonte ampliada.

## Validações executadas

- Suíte integral `pytest`: 676 testes e 10 subtestes aprovados.
- Gate oficial `release_tools.py ci --full`: 138 módulos em quatro partições, todos aprovados.
- Mobile 0.16.0: typecheck e testes de núcleo aprovados.
- Expo Doctor: 21/21 verificações aprovadas.
- Web: typecheck aprovado.
- Auditoria npm: nenhuma vulnerabilidade alta ou crítica; 13 ocorrências moderadas transitivas permanecem monitoradas por dependerem da matriz do Expo.
- Smoke test Python, verificação JavaScript, SBOM e matriz de compatibilidade 6.24.0: aprovados.
- Inspeção visual do Studio em 1280 × 720: versão, grade responsiva e área de prioridades aprovadas sem overflow horizontal.
- As verificações opcionais `ruff`, `pyright` e `pip-audit` ficaram indisponíveis porque esses executáveis não estão instalados no ambiente de release.

## Segurança da atualização

- Origem ensaiada: Studio 6.23.2.
- Destino: Studio 6.24.0.
- Migração de banco: nenhuma.
- Diretórios preservados: `data`, `.venv`, `venv`, `runtime` e `backups`.
- Backup pré-atualização e teste de restauração: aprovados.
- SQLite `quick_check`: `ok`; violações de chave estrangeira: 0.
- Rollback: não necessário.
- SHA-256 do banco antes e depois: `3623173778EAEE9C32BD390A45528F91FDC0B8977A0BCA80C8DA98827BDF720F`.

## Pacote do Studio

- Arquivo: `QuestFlow_Studio_6.24.0_UPDATE.zip`.
- Tamanho: 3.255.428 bytes.
- Entradas: 1.073, todas sob a raiz `QuestFlow/`.
- Conteúdo `data/`, bancos, caches, ambientes e segredos: ausentes.
- SHA-256: `A673B834905750CBD3E7AFA0E0A8C5780E002DD263205536537DFFE1C3D5B26C`.

## APK Android

- Arquivo: `QuestFlow_Mobile_0.16.0.apk`.
- Versão: 0.16.0 (`versionCode` 22), Expo SDK 57.
- Tamanho: 136.867.645 bytes.
- Estrutura ZIP/APK: 1.386 entradas, `AndroidManifest.xml` presente, cinco arquivos DEX e leitura integral aprovada.
- Evidência EAS: build `5f27da7e-f849-43bb-95f6-a1cdc93783a1`, status `FINISHED`.
- Aplicativo: `br.questflow.mobile`; distribuição interna; perfil `preview`/APK.
- SHA-256: `44743C2C5FE546C05CB4305EC5234796F340CD04999E12A1BCA699650546EE97`.
