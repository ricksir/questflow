# Validação — QuestFlow Studio 6.0.0

## Escopo

A 6.0.0 corrige a regressão que deixava a tela **Curadoria inteligente** com “Método não permitido” e implementa a segunda etapa do roadmap técnico: **FSRS + Bayesian Knowledge Tracing + IRT pessoal regularizada**.

## Correção crítica — “Método não permitido”

A interface 5.9 chamava recursos que já existiam no núcleo, porém 9 métodos não estavam na `ALLOWED_API_METHODS` do servidor HTTP local:

- `get_ai_commentary_brief`
- `get_bank_intelligence`
- `get_question_intelligence`
- `get_question_knowledge_graph`
- `get_rag_context`
- `get_semantic_index_summary`
- `resolve_duplicate_candidate`
- `start_ai_commentary_assist`
- `start_semantic_rebuild`

A 6.0 autoriza esses métodos e acrescenta os dois endpoints do novo modelo do aluno:

- `get_learning_model`
- `start_learner_model_rebuild`

Foi incluído teste de regressão que extrai todas as chamadas literais `bridge.call(...)` do JavaScript e falha se qualquer uma estiver fora da allowlist do servidor.

Também foi feito smoke test HTTP real em `/api/call`: `get_bank_intelligence`, `get_semantic_index_summary` e `get_learning_model` retornaram **HTTP 200 / ok=true** com a API real.

## Ajuste visual da aba

- O sidebar passou a usar largura responsiva maior.
- O rótulo **Curadoria inteligente** deixou de usar truncamento por ellipsis.
- O item aceita quebra natural quando necessário e continua compatível com o modo de sidebar recolhido.

## Modelo do Aluno 6.0

### FSRS

O FSRS existente foi preservado como **autoridade de agenda e precedência**. Correção, relearning, revisão vencida, nova e revisão antecipada continuam sendo os buckets rígidos de seleção.

### Knowledge Tracing

Foi adicionado Bayesian Knowledge Tracing (BKT) para estimar:

- probabilidade de domínio por conceito;
- confiança da estimativa em função da quantidade de evidências;
- lacunas prováveis e conceitos fortes.

Os conceitos são derivados de matéria, aula e assunto e, quando presente, do grafo de conhecimento da Curadoria 2.0 (tópico, referência legal e tags pedagógicas).

### IRT pessoal

Foi adicionada uma IRT 2PL online fortemente regularizada, que estima por matéria/questão:

- habilidade pessoal (`theta`);
- dificuldade do item (`b`);
- discriminação (`a`);
- informação do item;
- incerteza local.

A interface e o código deixam explícito que, sem uma coorte externa ampla, esses parâmetros são **pessoais e adaptativos**, não uma calibração psicométrica populacional.

### Fusão de prioridade

A nova prioridade combina:

- lacuna de domínio;
- confiança do KT;
- retrievability do FSRS;
- informação IRT;
- atraso de revisão.

Esse valor **não substitui o FSRS**: ele só influencia a ordenação dentro do mesmo bucket de precedência.

## Histórico existente e upgrade

A nova migração de estudo é a **v8**. O histórico bruto em `telegram_attempts` permanece como fonte de verdade.

Na primeira abertura com histórico 5.9, o QuestFlow detecta automaticamente tentativas ainda não refletidas no modelo e as processa em ordem temporal. Se uma sincronização inserir tentativas antigas fora de ordem, o modelo KT/IRT é reconstruído integralmente para preservar coerência temporal. O FSRS não é modificado pela reconstrução.

### Teste real 5.9.0 → 6.0.0

Foi criada uma base com o código original 5.9.0 contendo:

- 2 questões;
- 4 tentativas históricas;
- `question_bank` nas migrações `[1,2,3,4,5,6]`;
- `study` nas migrações `[1,2,3,4,5,6,7]`.

A mesma base foi aberta pela 6.0.0 e reconstruída. Resultado:

- questões preservadas: **2/2**;
- tentativas preservadas: **4/4**;
- `question_bank`: `[1,2,3,4,5,6]`;
- `study`: `[1,2,3,4,5,6,7,8]`;
- eventos do modelo: **4**;
- conceitos modelados: **5**;
- matérias com habilidade: **1**;
- questões com IRT: **2**;
- `PRAGMA quick_check`: **ok**;
- `PRAGMA foreign_key_check`: **0 violações**.

## Interface

O **Painel visual** ganhou o bloco “Modelo do aluno · FSRS + Knowledge Tracing + IRT”, com:

- domínio médio;
- confiança média;
- conceitos confiáveis/fortes;
- lacunas prováveis;
- questões modeladas;
- conceitos prioritários;
- habilidade pessoal por matéria;
- aviso metodológico sobre IRT pessoal.

O editor/inteligência da questão também mostra:

- domínio estimado (KT);
- confiança;
- dificuldade IRT pessoal;
- habilidade na matéria;
- informação do item.

Foi adicionado o botão **Reconstruir modelo do aluno** para replay manual auditável quando desejado.

## Testes finais

- Suíte completa: **266/266 testes aprovados**.
- Testes específicos 6.0: BKT, IRT, migração v8, backfill automático, prioridade de fusão, allowlist HTTP, smoke HTTP, rótulo da aba e vínculo do painel visual.
- `node --check web/app.js`: aprovado.
- `py_compile` dos módulos principais: aprovado.
- Smoke HTTP com a API real: aprovado.
- Migração 5.9 → 6.0 com dados: aprovada.

O aviso `TERM environment variable not set` observado ao final da suíte vem de uma rotina legada de limpeza de terminal executada no ambiente Linux de testes; não corresponde a falha funcional e a suíte terminou com `OK`.
