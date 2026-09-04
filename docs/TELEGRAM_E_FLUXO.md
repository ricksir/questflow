# Telegram e ciclo diário inteligente

## Fluxo diário

O agendador calcula a próxima ocorrência a partir de:

- horário `HH:MM`;
- dias da semana selecionados;
- registro dos ciclos já concluídos;
- data de ativação da configuração atual.

Antes do horário, o programa pode enviar um lembrete. No horário, cria um ciclo do tipo `diario`. Quando detecta um horário perdido após reinicialização, cria um ciclo do tipo `recuperacao`.

## Retentativas

Uma tentativa sem nenhuma questão enviada não conclui o ciclo diário. O agendador mantém o ciclo pendente e repete a tentativa conforme `flow_retry_minutes`.

Um ciclo parcial com ao menos uma questão enviada é registrado para evitar a repetição automática integral do mesmo ciclo.

## Botões e comandos

O menu usa teclado inline do Telegram e recebe eventos `callback_query`.

Dados utilizados:

- `qf:more:N` — bloco extra;
- `qf:cycle:N` — novo ciclo;
- `qf:stats` — desempenho;
- `qf:pause` — pausa;
- `qf:resume` — retomada.

O listener recebe `poll_answer`, `message` e `callback_query` por long polling.

## Registro das respostas

Cada enquete possui um `poll_id`. O banco relaciona o `poll_id` à questão e ao ciclo. Quando o usuário responde, o programa grava a alternativa, verifica o gabarito, atualiza acertos/erros e recalcula a próxima revisão.

## Funcionamento local

O Telegram não pode ser acionado por um computador completamente desligado. O QuestFlow registra a programação localmente e executa a recuperação na próxima abertura. Para envio contínuo sem depender do computador, o motor precisaria ser executado em um servidor sempre ligado.
