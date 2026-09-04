# Validação — QuestFlow Studio 5.7.1

## Correção principal

A falha observada no Windows ocorria durante a instalação do PyTorch, dependência
do `fsrs[optimizer]`, porque o ambiente virtual ficava dentro da pasta extraída.
Em caminhos como `Downloads\\QuestFlow_Studio_...\\.venv\\Lib\\site-packages\\torch...`,
a árvore interna do PyTorch podia ultrapassar o limite legado de caminho.

A 5.7.1 move o runtime para um caminho curto e estável:

- ambiente Python: `%LOCALAPPDATA%\\QFS\\venv`
- cache pip: `%LOCALAPPDATA%\\QFS\\pip-cache`
- marcadores de preparo: `%LOCALAPPDATA%\\QFS\\ready`

O banco de questões permanece na pasta `data` do QuestFlow; somente dependências
Python são compartilhadas fora da pasta do aplicativo.

## Escopo atualizado

Todos os BATs ativos que dependiam de `.venv` foram migrados para
`QUESTFLOW_RUNTIME.bat`: inicialização, instalação/diagnóstico, reparo,
interface clássica, validação do banco, conversão de base antiga, Turso,
Cloud Sync e suíte de testes.

O instalador também reconhece mensagens de Long Path e emite diagnóstico
específico em vez de tratar o caso como se fosse falha de proxy.

## Testes

- Compilação Python: OK, sem SyntaxWarning no `installer.py`.
- Testes específicos do runtime curto: 4/4 aprovados.
- Suíte completa: **248/248 testes aprovados**.
- Verificação de versão: `VERSION.txt`, `app.py`, `app_shared.py`, `pyproject.toml`
  e servidor local atualizados para 5.7.1.
- ZIP final verificado sem `.venv`, `__pycache__`, `.pyc` ou bancos de diagnóstico.

## Observação do ambiente de montagem

O ambiente de montagem não possui `fsrs[optimizer]` instalado; portanto o
`diagnostico.py` local acusa corretamente essa dependência como ausente. Na
máquina Windows do usuário, `INSTALAR_E_DIAGNOSTICAR.bat` instala e valida o
Py-FSRS + Optimizer dentro do runtime curto antes de concluir a preparação.
