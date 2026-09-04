# Validação técnica — QuestFlow Studio 6.8.0

## Escopo

Validação da evolução **Multimodal RAG 3.0**, da nova extração precisa da pesquisa Google e regressão integral da base 6.7.3.

## Resultado

- **410 / 410 testes automatizados aprovados** em execução isolada por módulo (93 + 101 + 112 + 104).
- **8 / 8 testes específicos da 6.8.0 aprovados**.
- 83 módulos de teste cobertos.
- compilação Python integral aprovada.
- `web/app.js` aprovado por `node --check`.
- smoke test de release aprovado.
- Python 3.13 disponível no ambiente e aprovado; 3.11/3.12/3.14 foram registrados como não disponíveis, sem falsa homologação.
- `pip-audit` não estava instalado no ambiente; a auditoria registra `unavailable` em vez de declarar ausência de vulnerabilidades.
- banco distribuído permanece compatível, sem nova migração.

## Casos específicos — pesquisa Google

- ruído de página (banca, ano, enunciado repetido, alternativas, menus, Fontes e Pesquisas relacionadas) é removido;
- somente a justificativa diretamente relacionada à questão é aceita;
- o bloco geral do Google não pode mais servir de fallback editorial;
- correspondência por código sem justificativa útil não encerra prematuramente a busca;
- fallback por enunciado exato e por consulta ampliada é executado quando necessário;
- página ainda instável recebe uma recaptura controlada;
- explicação abaixo do limiar de confiança é recusada;
- gabarito diferente vira alerta e não sobrescreve o banco.

## Casos específicos — Multimodal RAG 3.0

- recuperação `text`, `visual` e `hybrid` disponível no Knowledge Engine;
- grounding inclui fonte, modalidade e hashes auditáveis;
- caminhos absolutos locais não vazam nos descritores entregues à interface/auditoria;
- modo Equilibrado força mídia binária externa desabilitada;
- modo Personalizado exige opt-in explícito;
- adaptadores sem suporte binário não recebem anexos silenciosamente.

## Schemas

Nenhuma migração nova:

- `question_bank v8`
- `study v11`
- `ai_governance v4`

## Hotfix 1 — diagnóstico da Pesquisa Google visível

Foi corrigido um falso negativo no `diagnostico.py`: a versão 6.8.0 passou a usar uma diretiva de pesquisa mais específica (`gabarito + justificativa`, sem repetir enunciado/metadados/menus), mas o diagnóstico ainda procurava literalmente uma frase legada.

Validação adicional do hotfix:

- seção **Pesquisa Google visível** do diagnóstico: **OK**;
- **42/42 testes focados** aprovados (Google 6.7.2/6.8.0, enrichment e production hardening);
- novo teste garante que instalador e diretiva atual permaneçam sincronizados;
- `node --check web/app.js`: aprovado;
- compileall: aprovado;
- smoke test: aprovado;
- `PRAGMA quick_check`: `ok`;
- `foreign_key_check`: 0 violações.

A versão funcional permanece **6.8.0**; este pacote é um hotfix de distribuição/diagnóstico e não consome a evolução 6.8.1 do Roadmap.
