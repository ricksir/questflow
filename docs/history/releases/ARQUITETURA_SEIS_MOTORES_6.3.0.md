# Arquitetura de seis motores — QuestFlow Studio 6.3.0

A Etapa 5 preserva o desenho de **monólito modular com seis motores independentes em responsabilidade**. Não foram criados microserviços nem um sétimo motor.

## 1. Banco Editorial — `qf-editorial-engine-2`

Responsável por questões, proveniência, curadoria, publicação e agora pelo catálogo de versões legislativas. Publica questões geradas somente após o Governance Engine registrar aprovação humana.

## 2. Learner Model — `qf-learner-engine-1`

Permanece responsável por FSRS, Knowledge Tracing e IRT. Na Etapa 5, seu histórico chega ao gerador indiretamente por meio do perfil de aprendizagem/erros, sem misturar responsabilidade editorial com modelagem do aluno.

## 3. Learning Engine — `qf-learning-engine-2`

Mantém recomendação multiobjetivo e simulados adaptativos da Etapa 4. Não passou a gerar conteúdo; essa separação evita que o motor que escolhe a atividade também seja o autor da questão.

## 4. Knowledge Engine — `qf-knowledge-engine-2`

Fornece RAG/grafo e agora uma operação de **fontes selecionadas**. A geração recebe apenas os chunks explicitamente escolhidos. Versões legislativas indexadas pelo Banco Editorial tornam-se evidências recuperáveis.

## 5. AI Engine — `qf-ai-engine-2`

Executa:

- Tutor IA da Etapa 3;
- assistência editorial já existente;
- gerador controlado `qf-controlled-generator-1`;
- baseline fundamentado de questões ouro `qf-gold-grounded-baseline-1`.

O gerador não aprova o próprio conteúdo.

## 6. Evaluation & Governance Engine — `qf-ai-governance-2`

Executa auditoria, diagnóstico e avaliação independente. Na Etapa 5 acrescenta:

- crítico de geração `qf-generation-critic-1`;
- rascunhos e decisões humanas persistidos;
- perfil agregado de erros para orientar distratores;
- questões ouro e histórico de regressões;
- validação de vigência legislativa pela data da prova.

## Fluxo da Etapa 5

```text
Banco Editorial / Knowledge Engine
        │
        ├── fonte(s) selecionada(s)
        │
        ▼
     AI Engine
  gera rascunho
        │
        ▼
Evaluation & Governance
 crítico independente
        │
        ├── rejeitado/bloqueado → volta à edição
        │
        └── validado → aguarda decisão humana
                            │
                            ▼
                     aprovação humana
                            │
                            ▼
                     Banco Editorial
                         publica
```

## Legislação temporal

```text
chave canônica da norma
        │
        ├── versão A: início → fim
        ├── versão B: início → fim
        └── versão C: início → atual
                    │
              data da prova
                    │
                    ▼
       resolução da versão vigente
                    │
                    ▼
        fonte selecionável no RAG
```

Esse desenho permite estudar questões históricas sem substituir silenciosamente o texto que vigorava à época por uma versão legislativa atual.
