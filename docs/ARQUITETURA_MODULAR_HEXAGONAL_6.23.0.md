# Arquitetura modular e fontes de questões — QuestFlow 6.23.0

## Decisão

O QuestFlow é um monólito modular com arquitetura hexagonal e módulos verticais. O processo e o SQLite são únicos inicialmente, mas cada tabela possui exatamente um módulo proprietário. O registro aceita novos motores, submódulos, adapters e serviços transversais; os seis motores históricos são compatibilidade, não um limite.

O composition root está em `core/architecture/kernel.py`, os manifests em `core/architecture/modules.py` e a propriedade das tabelas em `core/architecture/ownership.py`. O diagnóstico `questflow.architecture.v3` informa qualquer tabela física ainda sem proprietário.

## Eventos, event store e projeções

Eventos internos são persistidos em `qf_internal_events` e capturados pela `qf_sync_outbox` existente. Um evento interno não implica event sourcing.

O `qf_event_store` aceita somente:

- `attempt`: tentativas;
- `learning`: eventos de aprendizagem;
- `sync`: sincronização;
- `ai_audit`: auditoria de IA.

Questões editoriais e configurações permanecem state-based. FSRS, KT, IRT e analytics são projeções reconstruíveis, registradas em `qf_projection_checkpoints`:

- `learner.fsrs_kt_irt`;
- `learning.analytics`.

## Contrato Studio v1

As rotas usam o token local `X-QuestFlow-Token` e envelopes `questflow.studio.v1`:

- `GET /api/v1/studio/contract`
- `GET /api/v1/studio/architecture`
- `GET /api/v1/studio/projections`
- `POST /api/v1/studio/projections/rebuild`
- `GET /api/v1/studio/questions`
- `GET /api/v1/studio/questions/{id}`
- `GET|POST /api/v1/studio/question-source`
- `POST /api/v1/studio/question-source/test`
- `POST /api/v1/studio/use-cases/{operation}`

O RPC `/api/call` continua disponível durante a migração. O frontend tipado reside em `web-src`, é compilado para `web/modules` e carrega fronteiras por rota; Configurações já usa diretamente o contrato v1.

## APIdasQuestões

A integração segue `https://www.apidasquestoes.com.br/documentacao` e usa por padrão `https://api.apidasquestoes.com.br/api/v1`.

No Studio, abra **Configurações → Fonte do catálogo de questões**, selecione **APIdasQuestões**, informe a API Key, teste e salve.

A API Key fica no backend em `api_das_questoes_credentials.dat`, cifrada por Windows DPAPI. Ela não entra no `config.json`, JavaScript, logs, URLs ou Mobile.

O adapter pagina em blocos oficiais de até 100, agrega páginas para a lista virtual atual, envia `x-api-key`, aplica filtros públicos, interpreta headers de quota e normaliza `label`/HTML/imagens e referências para o formato QuestFlow. Identificadores externos usam `api_das_questoes:{id}`.

Questões externas são `external_read_only`: podem ser pesquisadas e visualizadas no Studio, mas não são apresentadas como editáveis no SQLite local.

## Compatibilidade

- A fonte externa afeta somente o catálogo do Studio.
- O Mobile 0.15.5 continua em `/api/v1/mobile`, com snapshots, backlog, sincronização e uso offline existentes.
- Nenhuma API Key externa é enviada ao aparelho.
- O pacote 6.23.0 é uma atualização Studio-only e não exige novo APK.
