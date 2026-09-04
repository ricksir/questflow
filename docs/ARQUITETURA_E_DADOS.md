# Arquitetura e dados — QuestFlow Studio 2.1.4

## Componentes

### Interface

`app.py` usa Tkinter e reúne importação, revisão, ciclo diário, estatísticas, backup e configurações.

### Extração

`core/extractor.py` abre PDFs e imagens, executa OCR, identifica cabeçalhos, alternativas e gabaritos e gera questões normalizadas.

### Taxonomia

`core/spreadsheet_taxonomy.py` usa `data/taxonomia_afrfb.json`, gerado a partir das abas `MAPA_AF` e `CICLO_REG` da planilha AFRFB.

### Banco principal

`core/storage.py` gerencia questões, importações, deduplicação, migração e backup.

### Motor de estudo

`core/study.py` cria e mantém:

- `study_state`: envios, acertos, erros, sequência, próxima revisão e suspensão;
- `telegram_deliveries`: quiz, ciclo, `poll_id`, mensagem e estado do envio;
- `telegram_attempts`: alternativas escolhidas e resultado por usuário;
- `study_cycles`: ciclo diário, recuperação, bloco extra e novo ciclo solicitado;
- `flow_runtime`: ativação da agenda, lembretes, retentativas e cursor de rotação.

### Estratégia Auditor inteligente

A seleção é realizada em Python sobre os registros elegíveis do SQLite. Cada questão recebe prioridade com base em:

- revisão vencida;
- quantidade e proporção de erros;
- questão ainda não enviada;
- tempo desde o último envio;
- atraso da revisão;
- baixa exposição anterior.

Em seguida, o algoritmo agrupa por matéria, ordena os grupos por necessidade e percorre as matérias em rodadas. Dentro de cada matéria, tenta variar o assunto antes de repetir o mesmo tópico. Um cursor persistido altera o ponto inicial da rotação entre ciclos.

### Agendador

`core/flow.py` mantém duas threads daemon:

- agendador diário;
- long polling do Telegram.

O agendador usa o horário local do computador, dias da semana e a data de ativação da configuração. Registra ciclos concluídos para impedir duplicação. Quando um horário é perdido, cria um ciclo de recuperação. Falhas sem nenhum envio permanecem pendentes para nova tentativa.

### Telegram

`core/telegram.py` implementa:

- quiz nativo não anônimo;
- mensagens longas divididas em blocos;
- teclado inline com Mais questões, Novo ciclo, Desempenho e Pausar/Retomar;
- confirmação de `callback_query`;
- long polling por `getUpdates`.

## Repetição espaçada

- erro: nova revisão em aproximadamente 6 horas;
- acertos consecutivos: 1, 3, 7, 14, 30, 60 e 90 dias.

## Concorrência

- OCR executa fora da thread da interface;
- agendamento e listener executam em threads distintas;
- um lock impede dois ciclos simultâneos;
- cada operação abre e fecha sua própria conexão SQLite;
- o aplicativo sinaliza a parada antes de encerrar.

## Limite do modo local

Sem energia ou sem um processo em execução, não há código capaz de chamar a API do Telegram. Por isso, o programa envia o lembrete enquanto está ativo e realiza a recuperação quando volta a funcionar. Execução independente do computador exigiria um serviço em nuvem sempre ligado.
