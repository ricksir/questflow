# Validação técnica — QuestFlow Studio 6.8.3

## Resultado

- **443 / 443 testes automatizados aprovados** na regressão integral em 90 módulos isolados.
- Após o refinamento final de fallback de baseline/registro diário e tabela por matéria, **29 / 29 testes diretamente afetados** foram repetidos e aprovados.
- **5 / 5 testes específicos da 6.8.3 aprovados**.
- `web/app.js` aprovado pelo `node --check`.
- 170 arquivos Python presentes no pacote; módulos alterados compilados com sucesso.
- Smoke test: `quick_check = ok` e 0 violações de chave estrangeira.
- SBOM CycloneDX 1.5 atualizado para 6.8.3.
- Python 3.13.5 efetivamente validado; 3.14 permanece controlado/experimental quando indisponível.
- `pip-audit` registrado como `unavailable` quando não instalado, sem declarar falso zero de vulnerabilidades.

## Casos específicos 6.8.3

1. Histórico temporal deduplicado no mesmo dia, preservando pontos em dias diferentes.
2. Drift identifica chunks/fontes adicionados, removidos e alterados por fingerprint local.
3. Fingerprints não armazenam conteúdo bruto nem caminhos locais.
4. Observabilidade acompanha score, recall, grounding, cobertura, release, perfil e matéria.
5. Expansão do dataset Ouro apenas sugere candidatos; inclusão exige confirmação humana individual.
6. Relatórios JSON e CSV são exportáveis pela interface.
7. Baseline 6.8.2 pode servir como comparação inicial enquanto ainda não existe histórico observacional de duas releases.
8. Nenhuma nova migração SQLite; exatamente seis motores preservados.
