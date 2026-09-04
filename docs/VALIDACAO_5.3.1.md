# Validação — QuestFlow Studio 5.3.1

## Escopo

- identidade visual e assets responsivos;
- botão de reinício do ciclo;
- confirmação digitada;
- backup SQLite pré-reset;
- limpeza completa do progresso adaptativo e gamificação;
- preservação do banco de questões e correções pendentes;
- regressão da suíte existente.

## Resultado

- `python -m unittest discover -s tests -p "test_*.py"`: **157 testes aprovados**;
- `node --check web/app.js`: aprovado;
- `python -m compileall`: aprovado;
- assets de branding verificados no pacote.

O reset é transacional no banco ativo e o backup é criado antes da operação.
