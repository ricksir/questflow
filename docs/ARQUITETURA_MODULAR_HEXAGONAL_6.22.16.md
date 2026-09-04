# Arquitetura modular e fontes de questões — QuestFlow 6.22.16

## Decisão arquitetônica

O QuestFlow opera como **monólito modular com arquitetura hexagonal e módulos verticais**. O processo e o arquivo SQLite são únicos inicialmente, mas cada tabela tem exatamente um módulo proprietário. O registro aceita novos motores, submódulos, adapters e serviços transversais; os seis motores históricos são compatibilidade, não um limite.

O composition root é `core/architecture/kernel.py`. Os manifests e suas dependências ficam em `core/architecture/modules.py`; a propriedade de tabelas é declarada em `core/architecture/ownership.py`. O diagnóstico `questflow.architecture.v3` acusa qualquer tabela física sem proprietário.

## Limites de dados e eventos

- `editorial_bank` é dono do banco de questões, importações, catálogo e projetos de prova.
- `knowledge`, `learner_model`, `learning`, `ai` e `governance` são módulos verticais independentes.
- `mobile`, `integrations`, `runtime`, `sync` e `platform` são módulos/adapters transversais com tabelas próprias.
- Um módulo não deve escrever diretamente em tabela alheia; a integração ocorre por port/caso de uso ou evento interno.

Eventos internos são persistidos em `qf_internal_events`. Os triggers da Cloud Sync os inserem na `qf_sync_outbox`, preservando retry, deduplicação e sincronização já existentes. Publicar um evento não implica event sourcing.

O event store `qf_event_store` aceita somente os streams:

- `attempt` — tentativas;
- `learning` — eventos de aprendizagem;
- `sync` — sincronização;
- `ai_audit` — auditoria de IA.

Questões editoriais e configurações continuam state-based. Inserts canônicos de tentativas, learning events e interações de IA são capturados por triggers, sem transformar estados derivados em eventos.

## Projeções reconstruíveis

O catálogo `core/architecture/projections.py` registra:

- `learner.fsrs_kt_irt`: `study_state`, `concept_mastery`, `question_irt` e `learner_ability`;
- `learning.analytics`: `subject_analytics_daily` e dashboards que o consomem.

Checkpoints são registrados em `qf_projection_checkpoints`. As projeções podem ser consultadas e reconstruídas por casos de uso e pelas rotas Studio v1. O histórico canônico permanece a fonte; os estados derivados podem ser descartados e refeitos.

## API Studio v1

As rotas usam o mesmo token aleatório de sessão (`X-QuestFlow-Token`) e retornam envelopes `questflow.studio.v1`:

- `GET /api/v1/studio/contract`
- `GET /api/v1/studio/architecture`
- `GET /api/v1/studio/projections`
- `POST /api/v1/studio/projections/rebuild`
- `GET /api/v1/studio/questions`
- `GET /api/v1/studio/questions/{id}`
- `GET|POST /api/v1/studio/question-source`
- `POST /api/v1/studio/question-source/test`
- `POST /api/v1/studio/use-cases/{operation}`

`QuestFlowWebApi` mantém fachadas legadas para o Studio atual, mas listagem/leitura de questões, arquitetura, projeções, eventos e configuração de fonte já são despachadas pela application layer. `/api/call` continua habilitado durante a migração para evitar quebra do Studio; novas integrações devem usar `/api/v1/studio`.

O frontend tipado reside em `web-src` e é compilado para `web/modules`. O bootstrap observa a rota atual e carrega módulos sob demanda. A rota de configurações usa diretamente o contrato v1; páginas ainda não migradas usam um adapter de rota legado.

## APIdasQuestões

A integração usa a documentação oficial: `https://www.apidasquestoes.com.br/documentacao` e base `https://api.apidasquestoes.com.br/api/v1`.

Configuração no Studio:

1. Abra **Configurações → Fonte do catálogo de questões**.
2. Selecione **APIdasQuestões**.
3. Informe a API Key e, se necessário, ajuste URL base e timeout.
4. Use **Testar fonte** e depois **Salvar fonte**.

A chave fica no backend em `api_das_questoes_credentials.dat`, cifrada para o usuário Windows por DPAPI. Ela não entra em `config.json`, JavaScript, logs, Mobile ou parâmetros de URL.

O adapter envia `x-api-key`, pagina em blocos de até 100, suporta busca e os filtros públicos (`materiaId`, `bancaId`, `topicoId`, `ano`, `nivel`, `dificuldade`, entre outros), interpreta limites/quota dos headers e traduz erros 400/401/403/404/429.

Cada item externo é normalizado para as chaves já consumidas pelo Studio: `database_uid`, `codigo_origem`, `materia`, `assunto`, `banca`, `ano`, `enunciado`, `alternativas`, `gabarito`, `revisao`, `fonte` e `imagem_questao`. HTML é convertido para texto legível e os metadados/original HTML permanecem em `fonte`. O identificador local virtual tem a forma `api_das_questoes:{id}`.

Questões externas são marcadas `external_read_only`. O Studio pode buscar, filtrar e visualizar no formato atual, mas bloqueia edição local para não sugerir que alterou a fonte remota. A fonte SQLite continua sendo o padrão e funciona offline.

## Compatibilidade Studio e Mobile

- A escolha APIdasQuestões afeta a navegação do catálogo no **Studio**.
- O Mobile continua usando `/api/v1/mobile`, snapshots, backlog e SQLite/sincronização existentes; nenhuma API Key externa é exposta.
- Os contratos e tabelas atuais não foram removidos.
- O build TypeScript gera apenas módulos adicionais e não exige React/Vite em runtime.
- Antes de uma futura mudança do Mobile para catálogo remoto, deve existir um caso de uso específico que materialize snapshots revisados; o adapter externo não é chamado diretamente pelo aparelho.
