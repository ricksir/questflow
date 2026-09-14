# QuestFlow Studio 6.24.0 + QuestFlow Mobile 0.16.0

[![CI](https://github.com/ricksir/questflow/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ricksir/questflow/actions/workflows/ci.yml)

QuestFlow é um sistema local-first de banco editorial, estudo adaptativo e revisão no Mobile. O backend é um monólito modular com limites hexagonais, módulos verticais e um único SQLite com proprietário explícito para cada tabela.

## Arquitetura atual

- Registro extensível de módulos e motores, sem regra de quantidade fixa.
- Eventos internos duráveis em `qf_internal_events`, capturados pela outbox de sincronização existente.
- Event sourcing seletivo em `qf_event_store`: tentativas, eventos de aprendizagem, sincronização e auditoria de IA.
- FSRS, KT, IRT e analytics são projeções reconstruíveis.
- API versionada do Studio em `/api/v1/studio`; Configurações e a leitura do Revisar Banco (lista + detalhe) já usam o contrato v1 diretamente, enquanto o RPC `/api/call` permanece para fluxos ainda não migrados.
- Frontend do Studio com bootstrap e módulos por rota em TypeScript; a interface legada continua compatível.
- Fonte de questões selecionável entre o SQLite local e a APIdasQuestões, com resposta externa normalizada para o modelo QuestFlow.
- Mobile preservado em `questflow.mobile.v1` e `/api/v1/mobile`, incluindo uso offline e sincronização.

O desenho, os contratos e a configuração da APIdasQuestões estão em [docs/ARQUITETURA_MODULAR_HEXAGONAL_6.23.0.md](docs/ARQUITETURA_MODULAR_HEXAGONAL_6.23.0.md).

## Desenvolvimento

```powershell
# testes Python (use o Python com as dependências do QuestFlow)
python -m unittest discover -s tests

# frontend tipado do Studio
node mobile/node_modules/typescript/bin/tsc -p web-src/tsconfig.json

# Mobile
cd mobile
npm run typecheck
npm run test:core
```

Dados e credenciais não devem ser versionados. A API Key da APIdasQuestões é armazenada pelo backend com Windows DPAPI e nunca é enviada ao navegador ou ao Mobile.

O fluxo de branches, pull requests, dependências e proteção da `main` está documentado em [docs/GOVERNANCA_REPOSITORIO.md](docs/GOVERNANCA_REPOSITORIO.md).
