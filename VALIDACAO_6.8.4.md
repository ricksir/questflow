# Validação técnica — QuestFlow Studio 6.8.4

## Escopo

Validação da evolução **Retrieval Quality Gates + promoção segura de release** e regressão da base 6.8.3 Hotfix 1.

## Resultado

- **456 / 456 testes automatizados aprovados** em 92 módulos.
- Execução em quatro lotes de módulos isolados: **102 + 105 + 127 + 122** testes.
- **7/7 testes específicos da 6.8.4** aprovados.
- `node --check web/app.js` aprovado.
- compilação Python aprovada.
- CI local de release (`release_tools.py ci`) aprovado.
- lock exato e SHA-256 aprovados.
- smoke test aprovado.
- SQLite: `PRAGMA quick_check = ok` e **0 violações de chave estrangeira**.
- Python 3.13 efetivamente executado no smoke; 3.11/3.12/3.14 indisponíveis neste ambiente, sem falsa homologação.
- `pip-audit` permanece registrado conforme disponibilidade real do ambiente.

## Casos específicos 6.8.4

1. Release sem regressão fica `pass` e pode ser promovida somente por ação humana.
2. Queda acima dos thresholds coloca a release em `quarantine`.
3. Score, recall, grounding e cobertura possuem gates explícitos.
4. Promoção cria baseline aprovada separada da baseline de calibração.
5. Override exige justificativa humana mínima e fica auditado.
6. Rollback restaura baseline e perfil de retrieval aprovados anteriormente.
7. Relatório dos gates pode ser exportado em JSON/CSV.
8. Botão **Quality Gates** permanece sempre visível no topo de Revisar Banco.

## Banco e arquitetura

- nenhuma nova migração SQLite;
- `question_bank v8`, `study v11`, `ai_governance v4` preservados;
- Knowledge Engine: **3.4**;
- exatamente **seis motores** preservados;
- FSRS, KT e IRT mantêm suas autoridades originais.
