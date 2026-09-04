# Validação — QuestFlow Studio 6.9.9 / Mobile 0.6.0

## Resultado
Release validada para empacotamento.

- 492 testes Python aprovados em cinco partições da suíte completa.
- Testes específicos de Professional UX, Mobile Coach e Mobile Foundation aprovados.
- `npm run test:core` aprovado, incluindo o caso em que o cronômetro pausa fora da aba Questões e retoma ao retornar.
- Sintaxe TypeScript/TSX validada em 23 arquivos.
- JavaScript do Studio validado com `node --check`.
- HTML validado sem IDs duplicados e com rota/página `mobile` presentes.
- `python -m compileall` aprovado.
- `release_tools.py lock-check` aprovado.
- `release_tools.py smoke` aprovado: runtime 6.9.9 e SQLite de release íntegro.
- SBOM CycloneDX 1.5 gerado em `SBOM_6.9.9.cdx.json`.

## Correções adicionais encontradas na regressão
- Compatibilidade da linguagem de desconexão preservada: `Desconectar deste QuestFlow`.
- Cloud Bridge continua identificado no Studio como integrado, porém experimental/opcional.
- Recovery Guard do Cloud Sync passou a tolerar motores de teste/serviços sem atributo `database_path`, evitando queda do thread de watchdog.

## Proteção de dados
A release não contém nem substitui a base pessoal recuperada do usuário. A atualização é destinada à instalação fixa e deve preservar `data/`, inclusive `RECOVERY_GUARD.json`. O Cloud Sync/Turso não deve ser reativado automaticamente durante esta etapa.
