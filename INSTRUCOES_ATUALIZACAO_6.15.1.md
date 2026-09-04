# Instruções de atualização — QuestFlow Studio 6.15.1

## Objetivo do hotfix

A versão 6.15.1 corrige a ausência da seção **Estudos e Trilhas / Planilha de estudos e trilhas** na interface Web principal do QuestFlow. A lógica segura de catálogo/learner state introduzida na 6.15.0 é mantida.

## Como atualizar

1. Feche o QuestFlow Studio.
2. Abra o atualizador normal do QuestFlow.
3. Selecione `QuestFlow_Studio_6.15.1_UPDATE.zip`.
4. Aguarde backup, staging, smoke test e validação SQLite.
5. Abra o QuestFlow e confirme a versão **6.15.1**.
6. O Mobile permanece **0.10.1**.

## Onde trocar a planilha

Abra **Configurações**. A seção **Estudos e Trilhas** aparece logo abaixo de **OCR e processamento** e antes de **Rede e Proxy**.

Ela mostra a planilha ativa, faixa de trilhas, última sincronização, abas detectadas e versão do catálogo.

1. Cole o link da planilha nova em **Link da planilha de controle**.
2. Clique em **Testar planilha**. Esse passo é somente leitura e não altera banco nem URL ativa.
3. Revise o dry-run: correspondentes, atualizadas, novas, arquivadas e conflitos.
4. Se houver conflito, escolha explicitamente a correspondência ou marque como aula nova.
5. Clique em **Trocar/Atualizar planilha** e, no dry-run, confirme **Mesclar e usar nova planilha**.
6. O QuestFlow cria backup, executa a mesclagem segura e só então muda a fonte ativa.

## Segurança

Campos vazios da planilha nova não apagam progresso antigo. Aulas novas entram como não estudadas. Aulas removidas ficam arquivadas com histórico preservado. FSRS, Knowledge Tracing, IRT, learner model, respostas, sessões e histórico do Mobile não são resetados pela troca do catálogo.
