# Instruções de atualização — QuestFlow Studio 6.15.2

## Finalidade

A versão 6.15.2 corrige a falha intermitente observada na **primeira abertura do Studio imediatamente após uma atualização**, quando o Chrome era encontrado, mas não recebia conexão/heartbeat do motor local. A segunda abertura funcionava porque o processo órfão do Chrome já havia sido encerrado.

## Como instalar

1. Feche o QuestFlow Studio e o Mobile.
2. Abra o **QuestFlow Manager** pelo atalho normal.
3. Selecione o arquivo `QuestFlow_Studio_6.15.2_UPDATE.zip` pelo atualizador normal.
4. Aguarde backup, staging, smoke test e conclusão do Manager.
5. Quando o Manager oferecer a opção de iniciar, pode iniciar imediatamente: não deve mais ser necessário fechar tudo e abrir uma segunda vez.
6. Confirme a versão **6.15.2** no Studio.

## O que mudou

- o Manager passa a encerrar, antes de atualizar, somente o processo Chrome que utiliza o perfil privado do QuestFlow (`data\\chrome_runtime_5_4_0`);
- janelas normais do Google Chrome não são encerradas;
- o runtime aguarda o servidor HTTP local aceitar conexões antes de abrir a interface;
- se um Chrome órfão do QuestFlow ainda existir, ele é limpo defensivamente;
- se a primeira tentativa não produzir heartbeat, o QuestFlow faz uma segunda tentativa automática antes de mostrar erro.

## Banco, estudos e Mobile

- nenhuma migração nova de banco;
- nenhuma alteração no Course Catalog/Learner State da 6.15.1;
- nenhum reset de progresso, FSRS, KT, IRT, learner model ou sessões;
- Cloud Sync sem mudança de protocolo;
- Mobile permanece **0.10.1** e não é incluído no pacote UPDATE.
