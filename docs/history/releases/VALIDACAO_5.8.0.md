# Validação — QuestFlow Studio 5.8.0

Data de validação: 12/08/2026 (America/Sao_Paulo).

## Escopo

A versão 5.8.0 adiciona a camada **Curadoria Inteligente** ao banco de questões sem substituir FSRS, Learning Analytics, Telegram, importação, correção editorial ou Turso Cloud Sync.

## Validações executadas

- `python -m compileall -q .` — compilação Python concluída.
- `node --check web/app.js` — sintaxe JavaScript válida.
- `python run_tests.py` — **253 testes executados, 253 aprovados**.
- Smoke test da API local com banco temporário:
  - migrações `question_bank`: **1, 2, 3, 4, 5**;
  - criação e salvamento de questão manual: OK;
  - cálculo de qualidade editorial: OK;
  - cálculo de estado de curadoria: OK;
  - resumo da Curadoria Inteligente: OK.

## Regressões cobertas pela suíte

A suíte existente continuou validando, entre outros:

- FSRS 6 e aprendizado adaptativo;
- Learning Analytics e prioridades por matéria;
- Telegram, reenvios e fila de correção;
- importação PDF e extrator nativo QConcursos;
- correção/renomeação/arquivamento de questões;
- Turso Cloud Sync, modo offline e conflitos;
- inicialização/encerramento seguro e runtime Windows/Chrome;
- responsividade e componentes principais da interface.

## Testes específicos 5.8.0

Foram adicionados testes para:

1. classificação de origem e qualidade editorial;
2. dificuldade empírica por acertos e percepção do usuário;
3. deduplicação por similaridade sem exclusão automática;
4. leitura de tentativas reais e atualização do resumo do banco;
5. presença dos controles de Curadoria Inteligente, IA e duplicidade na interface.

## Observação de segurança editorial

O assistente de comentário gera **rascunho**. A geração não publica automaticamente e não substitui silenciosamente comentários humanos. O usuário precisa aceitar o rascunho no editor e ainda salvar/aprovar a questão.
