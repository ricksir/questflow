# Guia rápido — QuestFlow Studio 3.0.3

1. Execute `INSTALAR_E_DIAGNOSTICAR.bat`.
2. Abra `INICIAR_QUESTFLOW_STUDIO.bat`.
3. Configure o token do bot e detecte o Chat ID.
4. Importe PDFs, imagens ou um banco já salvo.
5. Revise somente as questões que permanecerem pendentes.
6. Configure o ciclo diário em **Fluxo Telegram**.
7. Mantenha 20 questões e a estratégia `auditor_inteligente` como ponto de partida.
8. Clique em **Salvar fluxo** e **Iniciar**.
9. Opcionalmente, execute `ATIVAR_INICIO_COM_WINDOWS.bat`.

## Aumentar ou reduzir as letras

Use `A−` e `A+` no cabeçalho. A alteração é imediata para textos, campos, tabelas e botões. A mesma escala aparece em **Configurações → Escala da interface**.

## Processar questões pendentes com releitura real

Na aba **Revisar banco**:

- selecione uma ou várias linhas com `Ctrl` ou `Shift` e clique em **Analisar selecionadas**; ou
- clique em **Analisar todas pendentes**.

Se o caminho antigo do PDF não existir, selecione a pasta onde os PDFs estão guardados. O programa localiza o arquivo pelo nome, recria o Markdown, força OCR em alta resolução e compara a questão pelo código, número e enunciado.

Em **Configurações → Análise avançada**, você pode:

- cadastrar uma pasta raiz dos PDFs;
- ajustar o DPI da análise apurada, padrão 300;
- permitir pesquisa web assistida durante o processamento.

## Pesquisar uma ou várias questões na internet

- **Web: questão selecionada** pesquisa somente a questão atual;
- **Web: várias pendentes** usa as linhas selecionadas ou pergunta quantas pendentes devem ser pesquisadas.

A janela final mostra o mecanismo de busca, a confiança e o endereço. Se nenhum resultado for extraído automaticamente, use **Abrir resultado/consulta** para abrir a pesquisa no navegador.

## Reenviar falhas do Telegram

Na aba **Fluxo Telegram**:

- selecione uma falha e clique em **Ver motivo**;
- use **Reenviar selecionada**;
- use **Reenviar todas com erro** para tentar novamente todas as falhas temporárias.

## Comandos no Telegram

Use `/mais`, `/ciclo`, `/desempenho`, `/status`, `/pausar`, `/retomar`, `/menu` ou os botões exibidos após cada ciclo.

Se o computador estiver desligado no horário, o aviso e o ciclo de recuperação só poderão ser enviados quando o computador e o programa voltarem a funcionar.


## Completar uma questão pela internet

1. Abra **Revisar banco** e selecione a questão.
2. Clique em **Web: questão selecionada**.
3. O programa pesquisa o código e diferentes trechos do enunciado em quatro mecanismos.
4. Ele só transcreve dados quando o código/enunciado confirmam que é a mesma questão.
5. Confira no resultado os campos aplicados, especialmente alternativas e gabarito.
6. Revise e clique em **Salvar e aprovar**.

Para várias questões, selecione-as com `Ctrl`/`Shift` e use **Web: várias pendentes**.

## Retirar uma questão anulada

1. Selecione a questão na revisão.
2. Clique em **Questão anulada** ou **Marcar anulada**.
3. Informe o motivo, se desejar.
4. Confirme. Ela sai da base ativa e deixa de ser enviada ao Telegram.
