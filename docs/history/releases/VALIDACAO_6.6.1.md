# Validação técnica — QuestFlow Studio 6.6.1

## Escopo

Release **6.6.1 — Evaluation & Governance 2.0**, baseada na 6.6.0. A mudança principal substitui a avaliação global predominantemente lexical por uma avaliação auditável por **afirmação → evidência → veredito**, mantendo os seis motores e todas as funcionalidades anteriores.

## Avaliador por afirmação/evidência

O `Evaluation & Governance Engine` foi atualizado para `qf-ai-governance-4`, com avaliador `qf-claim-evidence-evaluator-2`.

Para respostas de Tutor, comentários e fluxos governados, o avaliador:

1. segmenta a resposta em afirmações verificáveis;
2. identifica o tipo da afirmação e referências legais citadas;
3. procura a melhor evidência entre as fontes recuperadas;
4. classifica cada afirmação como `suporta`, `contradiz` ou `insuficiente`;
5. verifica alinhamento com gabarito oficial quando disponível;
6. verifica referências legais sem respaldo nas evidências;
7. verifica validade temporal de fontes legislativas contra a data de referência/prova;
8. persiste afirmações, evidências, confiança, alertas e resumo para auditoria.

## Persistência e migração

Nova migração **`ai_governance v4`**:

- `qf_ai_claims`;
- `qf_ai_claim_evidence`;
- `qf_gold_expectations`;
- `qf_gold_run_evaluations`;
- índices associados.

As Questões Ouro existentes recebem retropreenchimento de expectativas mínimas, inclusive referências legais requeridas quando deriváveis do item já armazenado.

Schemas preservados:

- `question_bank`: v8;
- `study`: v10;
- `ai_governance`: v1–v4.

## Questões Ouro

O baseline/regressão foi atualizado para `qf-gold-regression-2`. A regressão passa a registrar também:

- taxa de suporte das afirmações;
- quantidade suportada/contradita/insuficiente;
- alertas temporais;
- expectativas mínimas de grounding;
- referências legais obrigatórias quando aplicáveis.

## Geração controlada

O crítico evoluiu para `qf-generation-critic-2`. A alternativa correta e sua fundamentação passam pelo mesmo mecanismo de afirmação/evidência. A geração continua exigindo fontes selecionadas e aprovação humana; o avaliador não publica a própria saída.

## Interface

Tutor IA e Auditoria de IA exibem:

- resumo de afirmações suportadas/contraditas/insuficientes;
- cada afirmação individual;
- confiança/veredito;
- melhor evidência associada;
- estado temporal e alinhamento com gabarito quando aplicáveis.

## Upgrade real 6.6.0 → 6.6.1

Foi criada uma base pelo código original da 6.6.0 com interação de Tutor e Questão Ouro e, depois, a mesma base foi aberta pela 6.6.1.

Resultado:

- `ai_governance`: `[1,2,3] → [1,2,3,4]`;
- interação anterior preservada: **1/1**;
- Questão Ouro anterior preservada: **1/1**;
- expectativas Ouro retropreenchidas: **1**;
- nova interação gerou trilha persistida de afirmações/evidências;
- `PRAGMA quick_check = ok`;
- `PRAGMA foreign_key_check`: **0 violações**;
- arquitetura: **6/6 motores operacionais**.

## Testes automatizados

Discovery final: **337 testes**.

A execução integral foi particionada para respeitar o limite de tempo do ambiente, usando os mesmos testes descobertos:

- partição 1: **123/123**;
- partição 2: **102/102**;
- partição 3: **112/112**.

**Total: 337/337 aprovados.**

Incluíram regressões de:

- FSRS;
- Knowledge Tracing e IRT;
- incerteza/abstenção/calibração;
- Tutor IA;
- AI Gateway/privacidade;
- RAG e grafo;
- geração controlada;
- legislação temporal;
- Questões Ouro;
- Projeto/Edital;
- recomendador e simulados;
- Telegram;
- Turso/Cloud Sync;
- migrações e integridade SQLite;
- nova avaliação por afirmação/evidência.

## Validação estática e empacotamento

- módulos Python compilados em memória sem geração de `.pyc`;
- `web/app.js` validado com `node --check`;
- pacote final limpo de `__pycache__`, `.pyc` e caches temporários;
- manifesto de release com hashes SHA-256;
- ZIP validado com teste de integridade antes da entrega.
