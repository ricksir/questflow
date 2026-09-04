# QuestFlow Studio 5.7.0 — Validação Learning Analytics

## Escopo

A versão 5.7.0 evolui o painel de desempenho por matéria, a coleta metacognitiva do Telegram e a priorização usada pelo scheduler, preservando o FSRS 6 + Optimizer e as funcionalidades anteriores.

## Estrutura de dados

Foi adicionada a migração de estudo **v7**, idempotente e compatível com bancos existentes.

Novos campos em `telegram_attempts`:

- `perceived_difficulty` — `facil`, `media` ou `dificil`;
- `learning_gap` — sinal explícito de que o conteúdo precisa ser estudado/reestudado;
- `meta_updated_at` — momento da última atualização metacognitiva.

Nova tabela derivada `subject_analytics_daily`:

- matéria + dia;
- tentativas, acertos e erros;
- tempo médio de resposta;
- contagem de Fácil/Média/Difícil;
- contagem de lacunas de estudo.

A tabela pode ser reconstruída a partir do histórico de tentativas. Por isso não é tratada como fonte primária no Cloud Sync.

## Métricas implementadas

Por matéria, o painel calcula:

- desempenho histórico;
- desempenho das últimas 30 respostas;
- desempenho recente ponderado por recência;
- tendência recente x janela anterior;
- pontos semanais para sparkline;
- última revisão e dias sem revisar;
- retenção atual agregada pelo FSRS quando há cartão disponível;
- revisões vencidas, próximas de 7 dias e próximas de 30 dias;
- questões únicas praticadas;
- cobertura do banco;
- cobertura das aulas/conteúdos efetivamente estudados;
- confiança da amostra;
- pontos fracos por aula e assunto;
- sinais de dificuldade percebida e lacuna de estudo;
- meta e projeção até a prova, quando configurada.

## Prioridade inteligente

A prioridade por matéria usa um modelo explicável com os pesos aprovados:

- 35% risco de esquecimento/FSRS;
- 25% déficit de desempenho atual;
- 20% lacuna de cobertura;
- 10% recência;
- 10% urgência da prova.

Pressão de revisões vencidas e sinais metacognitivos refinam os componentes sem criar uma dimensão arbitrária separada.

O scheduler mantém sua hierarquia rígida de buckets:

1. correções;
2. relearning vencido;
3. revisões FSRS vencidas;
4. questões novas de conteúdo estudado;
5. antecipações permitidas.

Dentro desses limites, o risco da matéria passa a influenciar a distribuição, mantendo interleaving e penalização por repetição excessiva.

## Telegram

Foram acrescentados controles opcionais:

- `Fácil`;
- `Média`;
- `Difícil`;
- `Preciso estudar este conteúdo`.

Eles convivem com `Sabia / Dúvida / Chutei` e os tipos de erro existentes. Dificuldade percebida e lacuna de estudo servem à análise; não registram uma segunda revisão FSRS.

## Estado sem respostas

Foram testados dois casos diferentes:

- matéria estudada, porém ainda sem respostas: aparece como cold start acionável, sem percentual inventado;
- matéria ainda não estudada: aparece como **Aguardando estudo**, sem ser artificialmente priorizada.

## Testes

Comandos executados:

- `python -m compileall -q core ui web_api.py app.py app_classic.py diagnostico.py`
- `node --check web/app.js`
- `python run_tests.py`
- `python tests/performance_benchmark.py`

Resultado da suíte:

**244 testes executados — 244 aprovados.**

O diagnóstico confirmou o bloco:

`[OK] Learning Analytics 5.7: tendência, recência, cobertura, prioridade explicável e cold start`

Neste ambiente de montagem, a dependência externa `fsrs[optimizer]` não está instalada e o diagnóstico registra essa única falha externa. A integração FSRS continua exigindo a mesma dependência da 5.6.x e é verificada pelo instalador na máquina de destino.

## Desempenho sintético

Benchmark de 5.000 questões no ambiente de validação:

- importação: ~0,29 s;
- seleção adaptativa de 20/5.000: ~0,86 s;
- painel agregado existente: ~0,02 s;
- `subject_stats` Learning Analytics enriquecido, 12 matérias: ~0,05 s.

Os valores são de benchmark sintético e servem apenas para detectar regressões de desempenho, não como garantia de tempo em outros computadores.

## Integridade funcional

A suíte cobre, entre outros pontos:

- migração v7 e idempotência;
- tendência e peso maior para respostas recentes;
- prioridade combinando risco, desempenho, cobertura e recência;
- cold start estudado e não estudado;
- persistência dos novos sinais do Telegram;
- agregação diária por matéria;
- callbacks de dificuldade e lacuna de estudo;
- presença e estrutura dos componentes do novo painel;
- regressões de importação, banco, Telegram, FSRS, Cloud Sync, cobertura de estudos e interfaces.
