# Validação técnica — QuestFlow Studio 6.6.7

## Escopo
Correção da falsa pendência **Enunciado íntegro** em enunciados curtos e válidos de provas objetivas.

## Regra corrigida
- Foi removido o bloqueio por comprimento mínimo de 40 caracteres.
- A integridade do enunciado passa a ser contextual.
- Enunciados curtos são válidos quando possuem conteúdo textual e compõem uma questão coerente com alternativas/gabarito.
- Ausência objetiva de texto continua bloqueando a Curadoria.
- Sinais heurísticos de possível truncamento tornam-se alertas não bloqueantes, preservando a soberania da revisão humana.
- Gabarito e alternativas permanecem validações independentes.

## Caso reproduzido
`A imunidade tributária:` (23 caracteres) + alternativas A-D + gabarito válido:
- Enunciado íntegro: **SIM**
- Bloqueio crítico por tamanho: **NÃO**
- Conclusão humana da Curadoria: **PERMITIDA**, desde que os demais campos críticos estejam íntegros.

## Regressão
- **363/363 testes automatizados aprovados**.
- Partições: **91 + 90 + 99 + 83 = 363**.
- Testes específicos do novo validador: aprovados.
- Regressão de Curadoria 6.6.3–6.6.6: aprovada.
- Regressão de Cloud Sync idempotente: aprovada na suíte completa.
- `node --check web/app.js`: aprovado.
- Compilação em memória dos módulos Python: aprovada.

## Banco
Sem nova migração:
- question_bank: v8
- study: v10
- ai_governance: v4
