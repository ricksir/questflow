# StudyBatchService — QuestFlow 6.13.0

## Objetivo

Fazer o QuestFlow Mobile consumir a inteligência pedagógica do Studio/Core sem criar um segundo recomendador. A fonte autoritativa continua sendo `StudyRepository.select_questions`, que já combina FSRS, KT, IRT, learner fusion, cobertura, incidência de banca e prioridade adaptativa.

## Fluxo

```text
StudyRepository.select_questions
  └─ FSRS + KT + IRT + cobertura + banca + learner fusion
                │
                ▼
          StudyBatchService
          ├─ mix de sessão
          ├─ interleaving
          ├─ recent exposure guard
          └─ transferência de conceito
                │
        ┌───────┴────────┐
        ▼                ▼
     Studio/Core      Mobile API
                         │
                         ▼
                    Mobile 0.9.0
```

## Política Recomendado v2

1. Correções e relearning vencido continuam tendo precedência absoluta.
2. Revisões FSRS vencidas ocupam parte relevante do lote.
3. Quando houver conteúdo elegível, o lote reserva espaço para questões novas em vez de transformar Recomendado em Revisões.
4. Baixa/média confiança cria sinal de transferência para outra questão do mesmo conceito.
5. Itens vistos nas três últimas sessões recebem cooldown; o item que abriu a sessão anterior recebe penalidade adicional, salvo se for correção/relearning crítico.
6. A seleção final intercala matéria, assunto e aula.

## Modos

- `recommended`: política adaptativa mista.
- `review`: somente questões elegíveis para revisão/correção.
- `errors`: somente questões com histórico de erro, ordenadas pela inteligência central.
- `subject`: mesmo motor central, limitado à matéria escolhida.

## FSRS

A estimativa Bayesiana inicial de acurácia 0,50 continua disponível aos modelos preditivos, mas não é mais interpretada como evidência de baixa performance no rating FSRS. O parâmetro `prior_attempts` distingue ausência de histórico de histórico real ruim.

## Offline

O Mobile mantém pool local rotativo de até 120 questões já recebidas. Em ausência de conexão, prefere itens que não apareceram nas três últimas sessões antes de reutilizar questões recentes.

## Auditoria

Cada questão retorna:

```json
{
  "selection": {
    "policy": "recommended-adaptive-v2",
    "source": "StudyRepository.select_questions",
    "core_policy": "auditor_inteligente",
    "bucket": 2,
    "reason": "Revisão FSRS vencida",
    "recent_exposure_penalty": 0.0,
    "topic_transfer": false,
    "core_rank": 0
  }
}
```

Esses metadados são para consistência e auditoria do motor; não são métricas de desempenho do aluno.
