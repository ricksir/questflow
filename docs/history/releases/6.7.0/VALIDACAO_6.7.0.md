# Validação técnica — QuestFlow Studio 6.7.0

## Escopo da release

A 6.7.0 implementa:

- Tutor IA com scaffolding progressivo em seis níveis (0–5);
- registro do nível máximo de ajuda e do nível em que o aluno conseguiu resolver;
- sinal de dependência/independência incorporado ao Learner Model;
- prioridade pedagógica moderada para prática independente posterior quando houve alta dependência de ajuda;
- quatro representações de revisão: texto, flashcard, passo a passo e visual;
- contexto visual local para questões com imagem;
- transcrição/descrição visual opcional, submetida às regras de privacidade da IA;
- auditoria dos passos de scaffolding pelo Evaluation & Governance Engine;
- sincronização das sessões/eventos de scaffolding via Cloud Sync;
- migração incremental `study v11`.

## Regressão automatizada

A suíte final contém **379 testes automatizados**.

A validação foi concluída em partições independentes para evitar interferência entre threads/servidores de testes legados:

- Grupo 1: 113/113
- Grupo 2: 131/131
- Grupo 3A: 63/63
- Grupo 3B: 72/72

**Total: 379/379 aprovados.**

Avisos `ResourceWarning` de alguns testes legados de SQLite/socket permaneceram não-fatais e não produziram falhas.

## Migração real 6.6.8 → 6.7.0

Foi criada uma base usando o código original da 6.6.8, contendo 1 questão e 1 tentativa local. A mesma base foi então aberta pela 6.7.0.

Resultado:

- questões: 1/1 preservada;
- tentativas: 1/1 preservada;
- `study`: v10 → v11;
- `tutor_scaffold_sessions`: criada;
- `tutor_scaffold_events`: criada;
- `PRAGMA quick_check = ok`;
- `PRAGMA foreign_key_check`: 0 violações;
- seis motores: 6/6 operacionais.

Depois da migração foi iniciada uma sessão de scaffolding, avançada para o nível 1 e concluída nesse nível. A sessão e seus eventos foram persistidos e o Learner Model registrou independência de 0,8 no cenário de teste.

## API HTTP local

Foram exercitados pela rota real `/api/call`:

- `start_tutor_scaffolding` → HTTP 200;
- `advance_tutor_scaffolding` → HTTP 200;
- `get_tutor_scaffolding` → HTTP 200.

## Validação de sintaxe/empacotamento

- 152 arquivos Python compilados em memória sem erro;
- `web/app.js` validado com `node --check`;
- allowlist HTTP contém todos os métodos novos;
- schemas estruturados e governança das versões anteriores preservados;
- Cloud Sync inclui sessões/eventos de scaffolding;
- pacote final limpo de `__pycache__` e `.pyc` antes do ZIP.

## Schemas

- `question_bank`: v8
- `study`: v11
- `ai_governance`: v4
