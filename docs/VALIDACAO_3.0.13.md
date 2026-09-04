# Validação — QuestFlow Studio 3.0.13

## Escopo

Esta versão foi validada para três necessidades:

1. reenviar questões do Telegram que ficaram sem resposta;
2. recuperar solicitações de correção recebidas quando o programa estava fechado ou sem conexão;
3. mostrar quais aulas da planilha possuem questões, quais foram enviadas e quais ainda estão descobertas.

## Testes automatizados

A suíte executou **55 testes**, todos aprovados. Foram incluídos testes específicos para:

- detectar entrega enviada há mais de 24 horas sem resposta;
- não reenviar uma entrega já respondida;
- encadear o reenvio e marcar o envio anterior como `reenviado_sem_resposta`;
- limitar a quantidade de reenvios;
- persistir callbacks do Telegram antes do processamento;
- recuperar uma solicitação de correção pendente;
- persistir e reenviar mensagens da caixa de saída;
- distinguir aulas sem questões, com questões nunca enviadas e já enviadas;
- abrir a nova aba **Mapa de aulas** na interface.

Resultado completo: `docs/RESULTADO_TESTES_3.0.13.txt`.

## Teste gráfico

A interface foi aberta em monitor virtual e confirmou:

- criação da aba **Correções Telegram**;
- criação da aba **Mapa de aulas**;
- seleção múltipla e controles de revisão;
- escala de fonte em tempo real.

Resultado: `docs/RESULTADO_TESTE_INTERFACE_3.0.13.txt`.

## Diagnóstico do ambiente de construção

Os componentes internos, banco, OCR, Telegram, Google Modo IA, continuidade offline e mapa de aulas foram validados. O ambiente de construção não possuía os pacotes `pymupdf4llm` e `selenium` no índice local, por isso o diagnóstico registrou essas duas dependências como ausentes. Elas permanecem declaradas em `requirements.txt` e são instaladas pelo `INSTALAR_E_DIAGNOSTICAR.bat` no computador de destino.

Resultado: `docs/RESULTADO_DIAGNOSTICO_3.0.13.txt`.

## Limite operacional

Nenhum programa local consegue receber um clique enquanto o computador está desligado. O QuestFlow recupera o clique quando volta a funcionar se a atualização ainda estiver disponível no Telegram. Depois de recebida, a solicitação passa a ficar persistida no SQLite e não depende mais da disponibilidade do Telegram.
