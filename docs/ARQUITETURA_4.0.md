# Arquitetura QuestFlow Studio 4.0

## Objetivo

O QuestFlow 4.0 permanece **local-first**: banco, imagens, histórico, modelo adaptativo e configurações ficam no computador. A conexão externa é usada apenas quando o usuário ativa Telegram, atualização de planilha ou pesquisa assistida.

## Camadas

### Interface (`app.py`)

- shell responsivo com zoom, temas, barra lateral recolhível e painéis redimensionáveis;
- Painel adaptativo Mission Control;
- revisão, importação, mapa de aulas, correções Telegram, fluxo e configurações;
- trabalhos longos executados fora da thread principal e entregues por fila de eventos.

### Domínio

- `core/adaptive_engine.py`: memória, previsão, atualização incremental e prioridade;
- `core/study.py`: seleção, ciclos, respostas, correções e estatísticas;
- `core/flow.py`: agendamento, listener, retentativas e continuidade offline;
- `core/telegram.py`: composição visual, quizzes, cartões de explicação e tratamento de erros.

### Ingestão

- `core/markdown_pipeline.py`: PDF para Markdown com cache;
- `core/extractor.py`: texto nativo, OCR, imagens, metadados, alternativas e gabarito;
- `core/enrichment.py` e `core/google_browser.py`: enriquecimento opcional e confirmável.

### Persistência

- SQLite com WAL, `synchronous=NORMAL`, cache em memória, `mmap` e chaves estrangeiras;
- migrações aditivas para preservar bancos 3.x;
- tabelas separadas para questões, estudo, entregas, respostas, filas, modelo e exclusões.

## Motor adaptativo

O motor combina:

1. estado por questão: dificuldade, estabilidade, recuperabilidade e tempo médio de resposta;
2. curva de esquecimento inspirada em DSR/FSRS;
3. regressão logística incremental, atualizada localmente a cada nova resposta;
4. retenção-alvo configurável;
5. prioridade interpretável baseada em risco, vencimento, novidade, cobertura, correção e status.

Ele não pretende ser uma implementação oficial completa do FSRS. A escolha foi manter uma solução auditável, leve e sem dependências de aprendizado de máquina pesadas.

## Telegram

A explicação nativa do quiz é opcional e desativada por padrão. O fluxo principal envia:

1. cartão da questão;
2. enquete nativa;
3. cartão de resultado em resposta à enquete;
4. explicação completa em uma ou mais mensagens;
5. botões para corrigir, avançar e consultar desempenho.

## Resiliência

- backoff exponencial e `retry_after`;
- filas locais para callbacks e mensagens pendentes;
- deduplicação de respostas, correções e reenvios;
- quarentena de backlog antigo;
- limites por lote, sessão e dia;
- recuperação após reinício.

## Limites honestos

O QuestFlow é um aplicativo desktop Python/Tkinter. Ele foi reforçado com testes e práticas de engenharia, mas não é software certificado para missão crítica, não possui verificação independente formal e não é afiliado à NASA.
