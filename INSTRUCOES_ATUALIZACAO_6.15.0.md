# Instruções de atualização — QuestFlow Studio 6.15.0

## Atualização do programa

1. Feche o QuestFlow Studio e o Mobile Bridge em execução.
2. Use o atualizador normal do QuestFlow e selecione `QuestFlow_Studio_6.15.0_UPDATE.zip`.
3. O atualizador cria backup prévio do diretório `data`, valida SQLite, aplica o código em staging e executa smoke test.
4. Ao concluir, abra o QuestFlow e confirme no cabeçalho/versão que o Studio está em **6.15.0**.
5. O Mobile continua em **0.10.1**.

O pacote UPDATE não contém `data`, `node_modules`, `.expo`, caches ou a pasta Mobile, pois não houve alteração real no Mobile.

## Troca da planilha de trilhas

1. Abra **Configurações → Estudos e Trilhas / Planilha de estudos e trilhas**.
2. Cole o link da planilha nova ou selecione o XLSX.
3. Clique primeiro em **Testar planilha**.
4. Revise o dry-run: iguais, atualizadas, novas, removidas e correspondências incertas.
5. Se houver correspondência incerta, decida explicitamente se é a mesma aula, uma aula nova ou deixe para depois. A mesclagem fica bloqueada enquanto houver conflito sem resolução.
6. Clique em **Mesclar e usar nova planilha**.
7. O QuestFlow cria backup e somente muda a fonte ativa após a mesclagem e as validações finais.
8. Confira o relatório pós-mesclagem e, se desejar, exporte-o.

## Regra de segurança

Célula pessoal vazia na planilha nova não apaga progresso antigo. Aulas novas entram como não estudadas. Aulas removidas são arquivadas, com histórico preservado.
