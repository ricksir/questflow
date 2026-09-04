# Notas dos algoritmos adaptativos — 4.1

## Camadas de decisão

A seleção de uma questão não depende de uma única fórmula. O ciclo aplica, nesta ordem:

1. elegibilidade: status aprovado, não anulada, não suspensa;
2. prioridade operacional: correções resolvidas e revisões vencidas;
3. memória: probabilidade de recordação e estabilidade;
4. cobertura: matéria/aula/assunto pouco explorado;
5. diversidade: evita repetir o mesmo assunto no mesmo ciclo;
6. limite e segurança: quantidade diária, sessão e retentativas.

## FSRS e fallback

Quando `fsrs` está instalado, o adaptador usa `Scheduler`, `Card`, `Rating` e serialização JSON da API pública. O mapeamento do quiz binário é conservador:

- erro → Again;
- acerto lento ou histórico frágil → Hard;
- acerto normal → Good;
- acerto rápido com histórico forte → Easy.

Sem a extensão, o QuestFlow usa a curva DSR local já testada. O banco registra qual scheduler produziu o estado.

## Bandit de assuntos

A pontuação de assunto usa uma forma UCB:

```text
prioridade = fraqueza + risco de memória + exploração + recência + lacuna de cobertura
```

A incerteza diminui à medida que o assunto recebe respostas. Isso evita dois extremos: estudar apenas os assuntos ruins ou ignorar conteúdos novos.

## Modelo online

O classificador logístico local continua aprendendo com:

- estabilidade;
- tempo desde a revisão;
- dificuldade;
- acurácia histórica;
- tempo de resposta;
- questão nova;
- status autoaprovado.

Os pesos são limitados e regularizados. O modelo não envia dados para a nuvem.

## XP e níveis

O XP considera resultado, dificuldade, tempo, primeira tentativa e sequência. A curva de nível é sublinear:

```text
nível = floor(sqrt(XP / 75)) + 1
```

O objetivo é comunicar progresso, não criar compulsão. Erros recebem pequena pontuação porque geram informação útil para a revisão.

## Métricas recomendadas

Para avaliar o motor com histórico real:

- Brier score da previsão de recordação;
- log loss;
- retenção observada versus retenção-alvo;
- carga média diária;
- cobertura por aula/assunto;
- taxa de questões corrigidas após envio;
- latência e falhas do Telegram.
