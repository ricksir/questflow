# Validação — QuestFlow Studio 6.10.2 / Mobile 0.7.3

## Correção aplicada
- Corrigida a falha de atualização no Windows causada por caminhos de `mobile/node_modules` que atingiam o limite legado de 260 caracteres durante o staging.
- O pacote UPDATE não transporta `mobile/node_modules`, `.expo`, builds transitórios nem `data`.
- `extract_update_zip()` também ignora essas áreas caso um pacote futuro as inclua por engano.
- O atualizador externo passa a preferir o `questflow_update_runner.py` da instalação atual e usa o runtime antigo apenas como fallback.

## Evidência do erro reproduzido
- Caminho observado no erro do usuário: `...ZXingObjC.yml`.
- Comprimento calculado no staging do Windows: **260 caracteres**.

## Testes executados
- 14/14 testes focados em updater/Manager/hierarquia visual: aprovados.
- 67/67 testes de hardening, watchdog, retrieval, versões e visual 6.10.1/6.10.2: aprovados.
- Smoke test da aplicação: aprovado em Python 3.13.5; SQLite `quick_check`: `ok`; 0 violações de foreign key.
- Simulação de atualização usando o **runner e core da versão 6.10.0** para aplicar o pacote 6.10.2: aprovada.
- Na simulação, a versão mudou de 6.10.0 para 6.10.2, o banco de teste foi preservado e `rollback_performed` foi `false`.

## Pacote UPDATE
- Não contém `node_modules`.
- Não contém `data`.
- Mantém QuestFlow Mobile 0.7.3 e todas as alterações visuais entregues na 6.10.1.
