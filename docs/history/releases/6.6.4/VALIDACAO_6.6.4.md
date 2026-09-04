# Validação técnica — QuestFlow Studio 6.6.4

## Correção validada

Foi reproduzido o cenário em que questões já aprovadas pela revisão humana continuavam classificadas como `revisar` por permanecerem na faixa B de qualidade.

A 6.6.4 separa as duas dimensões:

- `quality_score` / A–D: enriquecimento editorial;
- `curation_status`: conclusão da Curadoria.

## Caso de reprodução com 18 questões

Foram criadas 18 questões com:

- campos críticos íntegros;
- revisão humana `aprovado`;
- ausência deliberada de alguns enriquecimentos opcionais, mantendo a nota B.

Resultado após `rebuild_bank_intelligence_derived()`:

- `needs_review`: **0**;
- `ready`: **18**;
- `quality_bands.B`: **18**;
- `human_review_ready_b`: **18**.

Isso demonstra que uma nota B não é mais confundida com revisão pendente.

## Proteções

A revisão humana NÃO supera:

- enunciado insuficiente;
- gabarito inconsistente;
- alternativas inválidas;
- matéria ausente;
- assunto ausente;
- bloqueio manual.

## Cloud Sync

Campos derivados/reconstruíveis de questões foram mantidos fora da outbox quando mudam isoladamente, incluindo:

- status/score derivados de Curadoria;
- dificuldade derivada;
- tags/referências legais materializadas;
- versão/data de indexação semântica.

## Testes

Suíte completa final: **351 / 351 testes aprovados**, executados em três partições de 117 testes.

Validações adicionais:

- `node --check web/app.js`: OK;
- compilação dos módulos Python alterados: OK;
- método `complete_curation_review` presente na allowlist HTTP: OK;
- testes históricos de Curadoria Reativa: OK;
- testes históricos de Cloud Sync: OK;
- reprodução com 18 questões: OK.
