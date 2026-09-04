# Atualização QuestFlow Studio 6.17.0 + Mobile 0.12.0

## 1. Atualizar o Studio

1. Feche o QuestFlow Studio.
2. Pelo atualizador normal, selecione `QuestFlow_Studio_6.17.0_UPDATE.zip`.
3. Aguarde backup, staging, validações e smoke test.
4. Abra o Studio e confirme **Versão 6.17.0**.

O pacote do Studio não contém `data`, não substitui a pasta `mobile` e não contém `node_modules`/`.expo`.

## 2. Atualizar as fontes Mobile

Na pasta instalada do QuestFlow, execute:

`ATUALIZAR_QUESTFLOW_MOBILE_0.12.0.bat`

O atualizador cria backup das fontes e preserva `node_modules`, `.expo`, `android` e `ios`. Se o TypeScript falhar, as fontes anteriores são restauradas.

## 3. Remover definitivamente o botão flutuante do Dev Client

O botão pertence à build nativa já instalada. Após atualizar as fontes, gere e instale **uma nova build 0.12.0**.

Para uso diário/offline, use:

`GERAR_APK_MOBILE_0.12.0_LIMPO_EAS.bat`

Para continuar usando Dev Client, use:

`GERAR_DEV_CLIENT_MOBILE_0.12.0_SEM_BOTAO_EAS.bat`

A geração EAS exige internet e autenticação. A build Preview é a recomendada para não exibir overlays de desenvolvimento.

## 4. Conferir o histórico offline

1. Abra Studio e Mobile e faça uma sincronização.
2. Responda uma ou mais questões com o Studio indisponível/rede desligada.
3. Reconecte o aplicativo ao Studio e sincronize.
4. Abra **Questões > Respondidas offline**.
5. Cada tentativa deverá aparecer como **Correta**, **Incorreta** ou **Aguardando**.
6. Use **Ver resultado e explicação** para consultar resposta marcada, gabarito e explicação devolvidos pelo Studio.

A questão que estiver aberta no momento da sincronização não interfere no histórico: todas as tentativas offline pendentes são reconciliadas.

## 5. Observação sobre respostas da versão 0.11.x

A 0.12.0 tenta recuperar tentativas antigas que possuam alternativa marcada e ainda não tenham feedback. Se o Studio já não possuir o `attempt_id` correspondente, a tentativa continuará como **Aguardando**; ela não será inventada nem marcada como correta/incorreta localmente.
