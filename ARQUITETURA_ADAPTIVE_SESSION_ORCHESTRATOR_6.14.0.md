# Adaptive Session Orchestrator — QuestFlow 6.14.0

## Objetivo

A 6.14.0 transforma a seleção adaptativa centralizada da 6.13.0 em uma sessão que pode se replanejar durante a execução. O Mobile permanece **Study Only** e não calcula FSRS, KT, IRT, domínio ou prioridade.

## Arquitetura

```text
FSRS + KT + IRT + Learner Model + Cobertura
                    │
                    ▼
       StudyRepository.select_questions
                    │
                    ▼
             StudyBatchService
                    │
                    ▼
       AdaptiveSessionOrchestrator
       ├─ objetivo da sessão
       ├─ micro-lotes (padrão: 3)
       ├─ prefetch do próximo lote
       ├─ replanejamento por evidência
       ├─ anti-loop
       ├─ prática intercalada
       └─ transferência conceitual
                    │
                    ▼
              Mobile 0.10.0
```

## Micro-lotes

A sessão recebe um objetivo e um micro-lote ativo. O próximo micro-lote pode ser pré-carregado. Quando o estado pedagógico muda de forma relevante, o prefetch antigo é invalidado e substituído.

O tamanho padrão é 3 questões e o limite permanece controlado pelo servidor. A meta total da sessão é independente do tamanho do micro-lote.

## Estratégias

O orquestrador pode usar perfis como:

- `balanced`: equilíbrio entre revisão, cobertura e novas questões;
- `consolidate`: reforço após evidência de lacuna ou misconception;
- `transfer`: prioriza variações do mesmo conceito para verificar transferência;
- `expand`: amplia cobertura quando o estado está estável.

O perfil é decisão do QuestFlow; o Mobile apenas executa a sessão.

## Evidência durante a sessão

A composição dos próximos micro-lotes pode usar sinais como:

- acerto/erro;
- confiança declarada;
- tempo ativo de resposta;
- questão pulada;
- correção solicitada;
- tópico ainda não estudado;
- histórico FSRS/KT/IRT mantido no Core.

Erro com confiança alta pode ser tratado como **misconception candidate**. Acerto com baixa/média confiança pode favorecer outra questão do mesmo conceito antes de repetir o mesmo item.

## Prefetch e invalidação

O prefetch reduz latência sem congelar a decisão pedagógica. Ele é reutilizado quando o estado continua compatível. Pode ser invalidado quando surge mudança relevante, por exemplo:

```text
prefetch Q4-Q6
    ↓
Q3 = erro + confiança alta
    ↓
perfil muda para consolidate
    ↓
prefetch Q4-Q6 é invalidado
    ↓
novo Q4-Q6 é calculado
```

## Anti-loop e prática intercalada

O orquestrador mantém a proteção de exposição recente da 6.13.0 e evita repetir mecanicamente a mesma questão ou o mesmo conceito. Isso não é um bloqueio absoluto: correção ou relearning realmente devido podem superar a penalidade.

A composição intercala matéria, assunto e aula quando houver alternativas pedagogicamente equivalentes.

## Itens triados

`question_correction_requested` e `topic_not_studied_reported` podem retirar a questão da meta efetiva da sessão. O item é substituído sem ser tratado como tentativa FSRS normal.

## Explicabilidade

Cada decisão é persistida em tabelas próprias de sessão/micro-lote/questão. O Studio pode consultar **Por que esta questão?** com motivo, perfil, revisão do plano e metadados de seleção.

Essa explicabilidade permanece no Studio e não é exibida como métrica de estudo no Mobile.

## Avaliação do algoritmo

A observabilidade não deve otimizar apenas acertos imediatos. A 6.14.0 prepara métricas para comparar retenção atrasada e domínio futuro. Amostras pequenas são marcadas como insuficientes e não devem gerar alegações causais.

## Contrato

O novo contrato de sessão é `questflow.mobile.adaptive_session.v1`. O contrato geral Mobile continua `questflow.mobile.v1` e a fronteira de produto permanece **Study Only**.
