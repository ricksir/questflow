# Validação — QuestFlow Studio 3.0.12

## Escopo

Implementação do encaminhamento de questões do Telegram para uma fila específica de correção no aplicativo desktop.

## Fluxo validado

1. A questão salva recebe `database_uid`.
2. O payload de `sendPoll` inclui uma `InlineKeyboardMarkup` com o botão **⚠️ Corrigir esta questão**.
3. O callback usa `qf:review:<uuid>`, respeitando o limite de 64 bytes.
4. O listener recebe `callback_query` e grava a solicitação em `telegram_review_requests`.
5. Cliques repetidos do mesmo usuário na mesma questão atualizam a solicitação ativa, sem criar duplicatas.
6. A interface exibe a nova aba **Correções Telegram** e um contador na barra lateral.
7. **Abrir e editar** seleciona a questão correspondente em **Revisar banco**.
8. **Salvar e aprovar** encerra automaticamente as solicitações ativas da questão.

## Persistência com o programa fechado

O listener é iniciado sempre que token e Chat ID estão configurados, mesmo com o agendador diário desativado. Atualizações que ocorrerem enquanto o programa estiver fechado são processadas na próxima abertura, dentro do prazo de retenção do Telegram. A mensagem original mantém o botão, permitindo novo clique caso o prazo expire.

## Testes executados

- 49 testes automatizados: aprovados;
- compilação de `app.py`, `diagnostico.py` e módulos `core`: aprovada;
- teste gráfico em monitor virtual: aprovado;
- criação, deduplicação, abertura e resolução da fila: aprovadas;
- callback do Telegram com confirmação e evento para a interface: aprovado;
- botão de correção presente no payload do quiz: aprovado.

## Observação do ambiente de construção

O diagnóstico funcional específico da versão foi aprovado. O diagnóstico completo do instalador não pôde ser concluído neste contêiner porque o índice local não disponibilizou `pymupdf4llm` e `selenium`. Esses pacotes permanecem em `requirements.txt` e são instalados pelo script do Windows antes do diagnóstico do usuário.
