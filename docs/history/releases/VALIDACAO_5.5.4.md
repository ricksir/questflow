# Validação — QuestFlow Studio 5.5.4

A versão 5.5.4 altera somente a ergonomia da importação contextual da cobertura dos estudos.

## Critérios

- clique simples em qualquer célula de uma linha pendente inicia `beginCoverageImport`;
- linhas cobertas não recebem comportamento clicável;
- seleção de texto não dispara a ação;
- controles interativos internos continuam protegidos;
- Enter/Espaço continuam disponíveis;
- coluna `Importar` removida da tabela;
- `Faltam adicionar` permanece como indicador;
- fluxo contextual do núcleo não foi alterado.

## Resultado

- **216 testes executados / 216 aprovados**.
- `node --check web/app.js`: aprovado.
- `python -m compileall`: aprovado.
- `python diagnostico.py`: concluído sem falhas locais.
