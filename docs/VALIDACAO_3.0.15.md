# Validação — QuestFlow Studio 3.0.15

## Problema corrigido

O pip exibia `WARNING: Cache entry deserialization failed, entry ignored` quando encontrava uma entrada inválida em seu cache local. Era um aviso do gerenciador de pacotes, não uma falha do QuestFlow.

## Alterações verificadas

- instalação com `--no-cache-dir`;
- atualização automática do pip removida;
- dependências validadas por hash do `requirements.txt`;
- marcador vinculado à versão e executável do Python;
- validação por importação dos módulos obrigatórios;
- validação por `pip check`;
- segunda execução pula downloads quando o ambiente permanece válido;
- reparo forçado disponível em `REPARAR_INSTALACAO.bat`.

## Resultado

O instalador não reutiliza o cache que causava o aviso e não reinstala os pacotes desnecessariamente. Erros reais continuam sendo exibidos com o marcador `[FALHA]`.
