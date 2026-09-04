# Validação técnica — QuestFlow Studio 6.7.1

## Escopo da release

A 6.7.1 implementa duas evoluções sobre a 6.7.0:

1. **Coleta de evidência acionável para o Learner Model**
   - o rótulo passivo “Coletar evidência” tornou-se uma ação real;
   - o programa explica que a abstenção **não é um erro**, mas falta de evidência suficiente para estimar domínio com confiança;
   - informa exposições atuais, confiança e quantidade recomendada de respostas diagnósticas;
   - seleciona questões do mesmo conceito por informação IRT, prioridade e novidade;
   - inicia uma prática diagnóstica restrita ao conceito;
   - as respostas alimentam normalmente FSRS + KT + IRT e a sessão pode encerrar antes da meta quando a evidência já se torna suficiente.

2. **Benchmark pedagógico do scaffolding**
   - cruza sessões do Tutor com tentativas posteriores reais;
   - observa retenção em janelas imediata, 1d, 3d, 7d e 30d;
   - compara pouco apoio, apoio moderado e apoio alto;
   - compara também as representações usadas no Tutor;
   - só apresenta tendência comparativa quando existe amostra mínima;
   - deixa explícito que se trata de associação observacional, e não prova causal.

## Regressão automatizada

A suíte final contém **385 testes automatizados**.

A validação final foi executada em três partições independentes:

- Grupo 1: **128/128**
- Grupo 2: **128/128**
- Grupo 3: **129/129**

**Total: 385/385 aprovados.**

Os avisos legados de `TERM`/console em alguns testes de interface permanecem não-fatais e não produziram falhas.

## API HTTP local

Foram adicionados e testados pela rota real `/api/call`:

- `get_evidence_collection_plan`;
- `start_evidence_collection`;
- `get_scaffolding_benchmark`.

Os três métodos respondem pelo mesmo servidor local utilizado pela interface.

## Banco e migração

A 6.7.1 **não exige nova migração**. A coleta de evidência reutiliza tentativas/simulações adaptativas existentes e o benchmark deriva dados das sessões de scaffolding e tentativas já registradas.

Schemas preservados:

- `question_bank`: v8
- `study`: v11
- `ai_governance`: v4

## Arquitetura

A release mantém **exatamente seis motores**. Não foi criado um “Evidence Engine” ou “Benchmark Engine”.

- Banco Editorial: `qf-editorial-engine-3`
- Learner Model: `qf-learner-engine-4`
- Learning Engine: `qf-learning-engine-6`
- Knowledge Engine: `qf-knowledge-engine-2`
- AI Engine: `qf-ai-engine-4`
- Evaluation & Governance: `qf-ai-governance-4`

## Validação de sintaxe e empacotamento

- **153 arquivos Python** da release foram compilados em memória sem gerar `.pyc`;
- `web/app.js` foi validado com `node --check`;
- os métodos novos estão na allowlist do servidor local;
- o pacote final é limpo de `__pycache__`, `.pyc`, cache Markdown e artefatos temporários de usuário antes da compactação;
- o ZIP final é validado com teste de integridade.
