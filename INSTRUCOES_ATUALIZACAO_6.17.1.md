# Atualização QuestFlow Studio 6.17.1

## Instalação

1. Feche o QuestFlow Studio.
2. Abra o atualizador normal do QuestFlow.
3. Selecione `QuestFlow_Studio_6.17.1_UPDATE.zip`.
4. Aguarde backup, staging, smoke test, teste de restauração e conclusão.
5. Abra o Studio e confirme **Versão 6.17.1**.

A atualização foi preparada para instalação direta sobre a 6.16.1 ou 6.17.0. O Mobile permanece **0.12.0** e não precisa ser atualizado.

## Novo comportamento do Tutor IA

- O rascunho passa a aparecer em um editor de texto.
- Use **Salvar alterações** para guardar sua revisão.
- O texto original da IA permanece disponível em **Ver texto original gerado pela IA**.
- Cada salvamento é registrado no histórico de auditoria e recalcula a avaliação independente.

## Depois de alterar uma questão em Revisar banco

Ao voltar ao Tutor, o QuestFlow compara o conteúdo atual da questão com o snapshot usado pela orientação.

Se houver diferença, aparecerá um aviso de que a orientação está desatualizada. A aprovação fica bloqueada. Use **Gerar novamente com a questão atual** para produzir uma nova orientação baseada na versão corrigida.

O rascunho antigo não é apagado: ele permanece na Auditoria de IA como histórico.

## Orientações antigas existentes antes da 6.17.1

Na primeira abertura após a atualização, o QuestFlow cria um baseline de conteúdo para as orientações antigas que ainda não possuíam snapshot. Isso evita falsos avisos causados apenas por timestamps técnicos do banco.

Esse baseline é marcado na Auditoria como **legado da atualização** e passa a servir para detectar mudanças reais feitas depois da 6.17.1. Nenhum texto antigo da IA é reescrito.
