# Relatório de validação — QuestFlow Studio 6.18.0 / Mobile 0.13.0

## Escopo

Validação das mudanças de workflow do Tutor IA, elegibilidade da Reserva Offline e UX Mobile.

## Testes funcionais executados antes do congelamento

- 102 testes pytest relacionados/regressão: **102 aprovados, 0 falhas**.
- subconjunto inicial da nova funcionalidade: 14 aprovados.
- testes Mobile/estáticos adicionais: 17 aprovados.
- `node --check web/app.js`: aprovado.
- Mobile TypeScript `tsc --noEmit`: aprovado.
- Mobile core tests: aprovado.
- smoke Python: versão 6.18.0 carregada com sucesso.

A suíte monolítica integral não é declarada como executada; a validação foi feita por conjuntos direcionados e de regressão para evitar o problema conhecido de processos auxiliares que podem permanecer abertos neste ambiente.

## Atualizador Mobile 0.12.0 -> 0.13.0

Executado em instalação de teste contendo `node_modules`, `.expo`, `android` e `ios` sentinelas.

Resultado:

- versão final 0.13.0;
- typecheck executado pelo atualizador: aprovado;
- `node_modules`: preservado;
- `.expo`: preservado;
- `android`: preservado;
- `ios`: preservado;
- backup das fontes anteriores: criado.

## Compatibilidade e supply chain

- Python disponível no ambiente: 3.13.5, smoke aprovado.
- Python 3.11/3.12/3.14: não disponíveis neste runtime; não são marcados como testados.
- SBOM CycloneDX 1.5: gerado.
- lock de dependências: íntegro.
- `pip-audit`: não disponível no runtime; relatório registra `unavailable`, sem falso positivo de aprovação.

## Garantias arquiteturais

- Learning Engine permanece no Studio.
- Reserva Offline não contém gabarito.
- questão respondida e ainda não vencida é excluída do pacote offline.
- aprovação do Tutor IA fecha o erro corrente; novo erro posterior reabre o fluxo.
- eliminação visual de alternativa não altera FSRS/KT/IRT ou resposta enviada.

## Validação final do pacote

A seção de hash, integridade do ZIP, simulação do atualizador seguro e preservação do banco de 1.292 questões é registrada em `VALIDACAO_FINAL_6.18.0.json` após o congelamento do ZIP exato.
