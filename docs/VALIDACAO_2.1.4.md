# Validação — QuestFlow Studio 2.1.4

## Falha corrigida

A versão 2.1.3 possuía `APP_VERSION = "2.1.3"`, mas o diagnóstico ainda comparava o valor com `"2.1.2"`. Por isso a instalação terminava com a mensagem **versão do aplicativo inconsistente**, mesmo com todas as dependências instaladas corretamente.

## Alteração

O diagnóstico passou a ler `VERSION.txt` e verificar automaticamente se ele corresponde ao valor de `APP_VERSION` em `app.py`. O instalador `.bat` também lê o mesmo arquivo para mostrar a versão correta.

## Verificações realizadas

- compilação de `app.py`, `diagnostico.py` e módulos de `core`;
- `VERSION.txt` contém `2.1.4`;
- `app.APP_VERSION` contém `2.1.4`;
- não há comparação fixa com `2.1.2` ou `2.1.3` no teste do módulo principal;
- o diagnóstico conclui a etapa do aplicativo como `QuestFlow Studio 2.1.4`.
