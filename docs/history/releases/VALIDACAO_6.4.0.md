# Validação técnica — QuestFlow Studio 6.4.0

## Escopo
- Curadoria inteligente redesenhada para mostrar prioridades acionáveis em vez de uma esteira apenas descritiva.
- Menu lateral compactado para eliminar rolagem vertical nas resoluções usuais e reduzir altura automaticamente em janelas menores.
- Tutor IA com seletor explícito de questão, tornando os botões Gerar orientação e Recalcular diagnóstico utilizáveis mesmo sem erro anterior.
- Integração multiprovedor: QuestFlow local/RAG, Google Modo IA, OpenAI API, Google Gemini API e Anthropic Claude API.
- Chaves externas protegidas por DPAPI no Windows; não são gravadas em texto no config.json.

## Testes
- 299/299 testes automatizados aprovados.
- Python: py_compile aprovado para módulos alterados.
- JavaScript: `node --check web/app.js` aprovado.
- API HTTP: novos métodos adicionados à allowlist local.
- Regressão: testes dos seis motores, Tutor IA, Curadoria, RAG, Turso, Telegram, FSRS/KT/IRT e Etapas 1–5 permaneceram verdes.

## Observações
- No Linux de testes, o cofre DPAPI deliberadamente não persiste chaves; no Windows, usa o mesmo mecanismo seguro já empregado pelo QuestFlow para credenciais sensíveis.
- O Google Modo IA permanece como padrão para preservar o comportamento anterior quando o usuário marca a opção de complementar com IA externa.
