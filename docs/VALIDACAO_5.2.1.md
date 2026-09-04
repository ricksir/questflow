# Validação técnica — QuestFlow Studio 5.2.1

## Defeito reproduzido e corrigido

O erro `501 Unsupported method ('{{GET')` foi reproduzido no servidor local por meio de uma conexão HTTP/1.1 persistente. A versão anterior respondia ao endpoint de heartbeat antes de ler o corpo `{}`. Esses bytes permaneciam no socket e eram interpretados como prefixo da próxima linha de requisição.

A correção aplicada:

1. lê e consome o corpo de **toda** requisição POST antes de retornar;
2. rejeita `Transfer-Encoding` e tamanhos inválidos;
3. remove o corpo desnecessário enviado pelo heartbeat do navegador;
4. mantém normalização defensiva de métodos com prefixos de pontuação;
5. garante JSON em erros das rotas `/api/*`.

## Navegador

- seleção exclusiva do executável `chrome.exe`;
- detecção por PATH, Registro do Windows e pastas padrão;
- ausência de fallback para Edge, WebView2 ou pywebview;
- perfil separado em `data/chrome_runtime_5_2_1`;
- extensões e proxy desativados na sessão do aplicativo;
- flags experimentais de GPU removidas.

## Testes executados

- 125 testes automatizados aprovados;
- teste de heartbeat com corpo `{}` seguido de GET na **mesma conexão**;
- teste de requisição bruta `{{GET` normalizada para GET;
- teste que impede seleção de `msedge.exe`;
- teste das flags do perfil Chrome isolado;
- compilação de `app.py`, `desktop_runtime.py`, `web_server.py` e `web_api.py`;
- validação sintática de `web/app.js`;
- diagnóstico integrado sem falhas locais.

## Integridade dos dados

O SHA-256 do banco `data/questflow_questions.sqlite` permaneceu idêntico ao da distribuição 5.2.0 recebida durante a correção.

> A abertura real no Windows/Chrome do computador do usuário precisa ser confirmada após a instalação, pois o ambiente de validação não é o mesmo computador.
