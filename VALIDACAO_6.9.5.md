# Validação QuestFlow 6.9.5 / Mobile 0.2.1

Escopo: ciclo de vida dos aparelhos Mobile, terminologia Conectar/Desconectar, reconexão sem duplicidade e remoção visual segura.

## Critérios validados

- a interface não usa mais “Revogar/Revogado” para aparelhos Mobile;
- **Desconectar** encerra todas as sessões remotas do aparelho sem apagar histórico de estudo;
- o `device_id` da instalação é persistido separadamente da sessão no SecureStore;
- ao parear novamente o mesmo aparelho com um novo QR, o mesmo registro é reativado;
- a reconexão não cria uma segunda linha para o mesmo `device_id`;
- **Remover da lista** só é permitido após desconectar e apenas oculta o registro;
- ocultar um aparelho não apaga o registro, sessões históricas, respostas ou métricas;
- um aparelho removido da lista volta a aparecer se for conectado novamente;
- o contrato público continua `questflow.mobile.v1`;
- o endpoint DELETE existente continua compatível, agora com semântica de produto “desconectar”.

## Testes

Suíte completa dividida em quatro partições: **481 testes aprovados** (115 + 116 + 122 + 128).

Teste específico: `tests/test_mobile_device_lifecycle_695.py`, cobrindo desconexão, invalidação do token antigo, reconexão, reutilização do mesmo registro, remoção visual e textos da UI.

## Checks de release

- `python -m py_compile`: OK;
- `node --check web/app.js`: OK;
- validação sintática dos quatro arquivos TypeScript alterados com `typescript.transpileModule`: OK;
- `release_tools.py lock-check`: OK;
- `release_tools.py smoke`: OK;
- SQLite: `foreign_key_check` sem violações;
- runtime reporta versão 6.9.5.

A checagem TypeScript completa com resolução de tipos Expo não foi executada porque `node_modules` do projeto Mobile não está presente no pacote de origem. Isso não impediu a validação sintática dos arquivos alterados.
