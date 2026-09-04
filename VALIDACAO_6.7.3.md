# Validação técnica — QuestFlow Studio 6.7.3

## Escopo

**Production Hardening / Build Reprodutível**, evolução prevista no Roadmap após a 6.7.2.

## Resultado da release

- **402 / 402 testes automatizados aprovados**, em quatro partições determinísticas: **118 + 90 + 105 + 89**.
- **10 / 10 testes específicos da 6.7.3 aprovados**.
- Smoke test do pacote aprovado.
- `PRAGMA quick_check(1)` do banco distribuído: **ok**.
- `foreign_key_check`: **0 violações**.
- `web/app.js` aprovado por `node --check` no ambiente de validação.
- Lock SHA-256 íntegro e com **7 dependências fixadas exatamente**.
- SBOM CycloneDX 1.5 gerado.
- Python **3.13.5** disponível no ambiente e aprovado no smoke test.
- Python 3.11, 3.12 e 3.14 não estavam instalados no ambiente de validação; a matriz registra isso como indisponibilidade, sem simular homologação.
- `pip-audit` não estava instalado no ambiente; a auditoria registra `unavailable` em modo normal e pode ser tornada obrigatória com `--strict-audit` em ambiente conectado.

## Controles implementados

- lock de dependências com versões exatas;
- SHA-256 do lock validado antes da instalação;
- SBOM CycloneDX 1.5;
- auditoria opcional/estrita via `pip-audit`, sem instalação ou download silencioso;
- matriz Python 3.11–3.13 e Python 3.14 controlado/experimental;
- backup SQLite pela API de backup do SQLite;
- SHA-256 por arquivo e manifesto de backup;
- `PRAGMA quick_check(1)` e `foreign_key_check`;
- teste real de restauração em diretório temporário;
- retenção diária/semanal/mensal configurável;
- atualização transacional com staging, proteção contra ZIP Slip, smoke e rollback;
- CI local reproduzível via `release_tools.py ci`;
- suíte completa mantida em `TESTAR_SUITE_COMPLETA.bat`.

## Segurança

O atualizador não extrai caminhos fora do diretório de staging. O diretório `data` não é substituído pelo conteúdo do ZIP. Falhas de smoke/`quick_check` acionam rollback do código e preservam o backup prévio.

O gabarito, a Curadoria, o RAG, o Tutor, FSRS, KT, IRT, Cloud Sync, Watchdog e o fluxo Google/IA da 6.7.2 foram preservados.

## Schemas

Nenhuma migração nova:

- `question_bank v8`
- `study v11`
- `ai_governance v4`
