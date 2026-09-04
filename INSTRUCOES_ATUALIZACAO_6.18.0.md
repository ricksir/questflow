# Instruções de atualização — QuestFlow Studio 6.18.0 / Mobile 0.13.0

## Ordem recomendada

1. Feche o QuestFlow Studio.
2. Pelo atualizador normal, aplique `QuestFlow_Studio_6.18.0_UPDATE.zip`.
3. Abra o Studio e confirme **Versão 6.18.0**.
4. Na pasta do QuestFlow, execute `ATUALIZAR_QUESTFLOW_MOBILE_0.13.0.bat`.
5. Confirme que o atualizador Mobile termina sem erro e preserva `node_modules` e `.expo`.
6. Para um APK Preview já instalado, execute `GERAR_APK_MOBILE_0.13.0_LIMPO_EAS.bat` e instale a nova build 0.13.0; o bundle de uma build Preview anterior não é substituído apenas pela atualização de fontes no computador.

## O que verificar no Studio

Em **Tutor IA**:

- a lista deve se chamar **Revisão de Erros com o Tutor IA**;
- deve existir a área **Erros Tratados**;
- após gerar/salvar/aprovar uma orientação, a questão deve migrar para Erros Tratados;
- se a mesma questão for errada novamente no futuro, deve voltar à fila de revisão.

## O que verificar no Mobile

1. Sincronize com o Studio para renovar a Reserva Offline.
2. Sem conexão/Studio disponível, responda uma questão da reserva.
3. A tela deve informar que a resposta foi salva localmente **sem spinner de feedback/conexão**.
4. Ao arrastar uma alternativa, ela deve mostrar risco forte e o rótulo **ALTERNATIVA ELIMINADA**.
5. Depois de reconectar, sincronize e consulte o resultado em **Respondidas offline**.

## Regra da Reserva Offline

A reserva 0.13.0 aceita somente:

- questões nunca respondidas; ou
- questões já respondidas cujo prazo de revisão calculado pelo Studio já venceu.

O Mobile não calcula o espaçamento por conta própria.

## Rollback

O atualizador do Studio mantém o mecanismo de backup/staging/smoke/restore já existente. O atualizador Mobile cria backup das fontes antes da substituição e preserva dependências, `.expo` e diretórios nativos.
