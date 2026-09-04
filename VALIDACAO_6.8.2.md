# Validação técnica — QuestFlow Studio 6.8.2

## Escopo

Validação da evolução **Reranking calibrado + regressão contínua de retrieval**, preservando Multimodal RAG 3.0, Benchmark 6.8.1 e todos os hotfixes da pesquisa Google/editor.

## Resultado

- **438 / 438 testes automatizados aprovados** em 89 módulos isolados.
- **6 / 6 testes específicos da 6.8.2 aprovados**.
- `web/app.js` aprovado pelo `node --check`.
- **168 arquivos Python** presentes e compilação/smoke aprovados.
- `requirements.lock` íntegro por SHA-256.
- SBOM CycloneDX 1.5 atualizado para 6.8.2.
- Python 3.13.5 disponível e aprovado no smoke; 3.11/3.12 não disponíveis no ambiente; 3.14 permanece experimental/controlado.
- `pip-audit` não instalado no ambiente, registrado como `unavailable` sem declarar falsamente ausência de vulnerabilidades.
- SQLite: `PRAGMA quick_check = ok` e 0 violações de chave estrangeira.

## Casos específicos 6.8.2

- reranking usa features e pesos explícitos;
- consulta lexical pode superar score bruto quando a evidência é mais aderente;
- calibração compara grade fixa de perfis candidatos;
- calibração **não aplica** pesos automaticamente;
- histórico do perfil permite rollback humano;
- baseline e regressão detectam quedas globais e por matéria;
- endpoints locais e botão `Calibrar retrieval` estão expostos na UI.

## Política

A função de calibração recomenda configurações; a promoção continua dependente de confirmação humana. FSRS, KT e IRT não recebem alterações a partir do reranking.
