# Contribuindo com o QuestFlow

O repositório contém o código-fonte do QuestFlow Studio e do QuestFlow Mobile. Dados reais, backups, credenciais e artefatos de instalação permanecem fora do Git.

## Antes de alterar

1. Confirme que está trabalhando nesta cópia-fonte, não na instalação em `C:\Users\user\QuestFlow`.
2. Abra uma issue usando o modelo de problema ou melhoria.
3. Para pedidos ao Codex, use o roteiro em [`docs/GUIA_PEDIDOS_CODEX.md`](docs/GUIA_PEDIDOS_CODEX.md).
4. Crie uma branch curta, como `fix/importacao-pdf` ou `feat/painel-prioridades`.

## Ambiente

- Python 3.11 ou superior; a CI usa Python 3.12.
- Node.js 24 e `npm` para Mobile e módulos web.
- Dependências Python de desenvolvimento fixadas em `requirements-dev.lock`.
- Dependências JavaScript fixadas em `mobile/package-lock.json`.

Instale as dependências sem copiar dados da instalação real:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
Set-Location mobile
npm ci
```

## Validação local

Na raiz do repositório:

```powershell
.venv\Scripts\python.exe run_tests.py
npm --prefix mobile run typecheck
npm --prefix mobile run test:core
npm --prefix web-src run typecheck
```

Antes de abrir um pull request, execute também o fluxo alterado manualmente. Mudanças visuais devem incluir capturas nas larguras relevantes; mudanças de dados devem demonstrar preservação do banco e compatibilidade.

## Regras de segurança

- Nunca versione `data/`, bancos SQLite, backups, logs, tokens, QR codes, credenciais, chaves de assinatura ou arquivos `.env`.
- Nunca versione APKs, ZIPs de atualização, diretórios de build ou `node_modules`.
- Não use dados inventados em gráficos de produção. Estados sem dados precisam ser explícitos.
- Não altere diretamente a cópia instalada. Entregas passam pelo empacotamento e pelo atualizador seguro.

## Pull requests

Mantenha cada PR focado em um problema. Explique o resultado para o usuário, indique os testes executados e registre riscos de migração, sincronização ou compatibilidade. A integração contínua precisa estar verde antes da incorporação.
