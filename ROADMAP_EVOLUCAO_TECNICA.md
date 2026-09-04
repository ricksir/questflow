# Roadmap de evolução técnica do QuestFlow

## Etapa 1 — 5.9.0 — concluída

**Curadoria 2.0 + Deduplicação Semântica + Grafo + RAG Híbrido**

- proveniência e qualidade da 5.8 preservadas;
- assinatura semântica local e pré-indexada;
- deduplicação híbrida auditável;
- taxonomia em grafo;
- chunks RAG e reranking híbrido;
- mapa de conceitos e evidências híbridas na interface;
- contexto local incorporado à assistência de IA;
- funcionamento offline-first.

## Etapa 2 — 6.0.0 — concluída

**Learner Model: FSRS + Knowledge Tracing + IRT**

- FSRS preservado como motor de memória/revisão e autoridade de precedência;
- estado de domínio/confiança por conceito com BKT;
- IRT 2PL online regularizada para dificuldade, discriminação, informação e habilidade pessoal;
- separação entre “lembra a questão” (FSRS) e “domina o conceito” (KT);
- confiança cresce com evidência e baixa amostra é sinalizada explicitamente;
- prioridade de fusão alimenta a seleção apenas dentro da precedência FSRS.
- reconstrução completa a partir do histórico bruto de tentativas.

## Etapa 3 — 6.1.0 — concluída

**Tutor IA, diagnóstico de erros e arquitetura de seis motores**

- tutor socrático, rápido, professor e banca-específico;
- classificação probabilística de erro: conteúdo, confusão, exceção, interpretação, cálculo, desatenção, chute, memória e leitura incompleta;
- resposta contextualizada por FSRS + KT + IRT + tentativa recente + RAG + grafo;
- avaliador separado da IA que gera o comentário;
- auditoria de prompt/hash, provedor/modelo, fontes, resposta, avaliação e aprovação humana;
- outputs de IA permanecem rascunho até decisão humana;
- seis fronteiras explícitas: Banco Editorial, Learner Model, Learning Engine, Knowledge Engine, AI Engine e Evaluation & Governance Engine;
- API de Curadoria/Modelo do Aluno/Conhecimento redirecionada para os motores;
- funcionamento local preservado e provedor online opcional.

## Etapa 4 — 6.2.0 — concluída

**Recomendador multiobjetivo + simulados adaptativos**

- FSRS preservado como autoridade de precedência entre classes de revisão;
- score multiobjetivo explicável: domínio KT, esquecimento FSRS, cobertura, banca, IRT, urgência, incerteza e recência;
- modos Equilibrado, Diagnóstico, Revisão e Cobertura do edital;
- diversificação por matéria, aula, assunto e banca;
- simulado recalculado questão a questão após atualizar FSRS + KT + IRT;
- histórico de simulado integrado ao aprendizado, separado da operação Telegram;
- projeções por matéria com intervalos de confiança e ressalva explícita de que não são probabilidade de aprovação;
- incidência de banca calculada de forma transparente sobre o banco local;
- Learning Engine evoluído sem criar um sétimo motor.

## Etapa 5 — 6.3.0 — concluída

**Geração controlada + legislação temporal + questões ouro**

- geração de questões inéditas bloqueada sem seleção explícita de fontes do Knowledge Engine;
- snapshot das fontes e proveniência persistidos com cada rascunho;
- segundo avaliador interno independente (`qf-generation-critic-1`) valida suporte do gabarito, unicidade de alternativas, referências legais, cobertura das fontes e consistência temporal;
- distratores usam o perfil de erros recorrentes registrado pelo Evaluation & Governance Engine;
- versões legislativas possuem chave canônica, início/fim de vigência e resolução pela data de referência/prova;
- legislação versionada é indexada no RAG e pode ser usada como fonte selecionada;
- conflito entre data da prova e vigência da norma bloqueia a aprovação do rascunho;
- publicação exige aprovação humana explícita e preserva origem `inedita_propria`;
- banco permanente de questões ouro e regressões persistidas para acompanhar estabilidade da IA;
- arquitetura permanece com exatamente seis motores; a Etapa 5 foi distribuída entre Banco Editorial, Knowledge Engine, AI Engine e Evaluation & Governance Engine.


## Consolidação — 6.4.1 — concluída

**Hardening multiprovedor + monitor quinzenal consent-first**

- provedor padrão local/RAG e persistência externa stateless quando suportada;
- compatibilidade preventiva com parâmetros por modelo/provedor;
- retry limitado para falhas transitórias;
- token Telegram protegido por DPAPI no Windows;
- monitor de mudanças em fontes oficiais duas vezes por mês, sem acesso ao SQLite;
- agenda configurável, lembrete com consentimento, adiar/pular ciclo e histórico local;
- funcionamento offline preservado: falha de rede não trava a interface nem resolve a janela;
- pacote e versionamento consolidados antes das próximas evoluções do Projeto de Concurso/Edital.


## Etapa 6 — 6.5.0 — concluída

**Projeto de Concurso/Edital + retificações + atualidade + Central Hoje**

- concurso ativo como contexto central para cobertura, prioridade e recomendações;
- cadastro de órgão, cargo, banca, data da prova e observações;
- versionamento do edital/retificações com diff de inclusão, remoção e alteração;
- parser conservador do conteúdo programático e mapeamento questão↔item do edital;
- cobertura, estudo e domínio por item com dados reais do banco e KT;
- Central “O que fazer hoje?” integra FSRS, KT, IRT, lacunas do edital, cobertura e simulado;
- estados temporais de questões e bloqueio seguro das desatualizadas/anuladas/controversas na seleção normal;
- varredura temporal vinculada à legislação versionada;
- sincronização Turso dos dados editoriais do projeto, sem apagá-los no reset do ciclo;
- arquitetura permanece com exatamente seis motores.

## Consolidação — 6.5.1 — concluída

**AI Gateway + Structured Outputs + Prompt Injection Defense + Centro de Privacidade + Telemetria**

- Structured Outputs por JSON Schema nas APIs REST compatíveis de OpenAI, Gemini e Claude;
- AI Gateway interno ao AI Engine, sem criação de sétimo motor;
- Centro de Privacidade com modos Privado, Equilibrado e Personalizado;
- minimização explícita de matéria/assunto/banca, enunciado, alternativas, gabarito, RAG, Learner Model, pergunta e notas;
- prévia no Tutor do conteúdo que será compartilhado antes da geração;
- RAG/documentos tratados como `untrusted_data`, com detecção e sanitização de prompt injection;
- `ai_governance v3` para observabilidade de provedor/modelo, latência, tokens, Structured Outputs, sinais de injeção e custo estimado;
- custos calculados apenas com preços informados pelo usuário, evitando tabela comercial desatualizada;
- modo privado também bloqueia Curadoria online e Google Modo IA;
- funcionamento local/RAG e human-in-the-loop preservados.

## Consolidação — 6.5.2 — concluída

**Cloud Sync diagnosticado + autorrecuperação da outbox**

- painel distingue igualdade da contagem de questões de sincronização integral do banco;
- fila pendente detalhada por tabela/tipo/operação, com último erro e número de tentativas;
- sincronização manual/background drena a outbox em rodadas limitadas;
- eventos legados estruturalmente impossíveis de enviar são preservados em dead-letter local e deixam de bloquear a fila válida;
- diagnóstico permanece local-first e não altera os seis motores.

## Etapa 7 — 6.6.0 — concluída

**Learner Model com incerteza, abstenção, calibração e recomendações contrafactuais**

- Learner Model atualizado para `qf-learner-engine-2` e modelo `qf-learner-2`;
- Learning Engine atualizado para `qf-learning-engine-4` e recomendador `qf-multiobjective-2`;
- predição seletiva combina KT, FSRS, IRT pessoal e histórico conforme a evidência disponível;
- estados explícitos: estimativa confiável, estimativa cautelosa e evidência insuficiente;
- em evidência insuficiente o QuestFlow se abstém de classificar domínio e prioriza coleta diagnóstica;
- `study v10` persiste probabilidade pré-resposta, confiança, intervalo, decisão de abstenção e versão do Learner Model;
- backfill cronológico de bases 6.5.x cria previsões históricas sem alterar tentativas ou cartões FSRS;
- calibração do Learner Model mede Brier Score, ECE, cobertura e taxa de abstenção;
- plano contrafactual BKT estima perguntas diagnósticas/práticas de consolidação para um alvo de domínio, sem promessa causal;
- Tutor IA respeita a abstenção e não utiliza KT de baixa evidência como prova de domínio;
- arquitetura permanece com exatamente seis motores.

## 6.6.1 — concluída

**Evaluation & Governance 2.0 por afirmação/evidência**

- respostas da IA são decompostas em afirmações verificáveis;
- cada afirmação é ligada à melhor evidência disponível e classificada como suportada, contradita ou insuficiente;
- gabarito oficial, referências legais e vigência temporal entram na avaliação;
- Tutor e Auditoria mostram a trilha de afirmações/evidências;
- Questões Ouro registram expectativas de grounding e avaliações por execução;
- Gerador Controlado usa o mesmo avaliador independente antes da decisão humana;
- o modelo gerador continua sem autoridade para aprovar a própria saída.

## 6.6.2 — concluída

**Cloud Sync idempotente para dashboards/recomendações**

- corrigido o ciclo em que atualizar o painel recriava centenas de eventos `study_state`;
- pré-visualizações do Recomendador/Central Hoje são estritamente read-only;
- métricas transitórias e recalculáveis não geram Cloud Sync;
- mudanças duráveis de FSRS/progresso continuam sincronizadas;
- UPDATEs sem mudança efetiva deixam de gerar ruído na outbox;
- regressão reproduziu exatamente `0 → 213` na 6.6.1 e `0 → 0` na 6.6.2.

## 6.7.0 — concluída

**Tutor IA com scaffolding progressivo + revisão multimodal**

- transformar o modo socrático em uma escada de pistas graduais antes da explicação completa;
- registrar em qual nível de ajuda o aluno conseguiu prosseguir e usar esse sinal no Learner Model;
- suportar revisão orientada por diferentes representações do material, mantendo RAG e governança;
- ampliar fluxos para transcrições/imagens quando houver fonte compatível e permissão explícita;
- preservar privacidade, avaliação por afirmação/evidência e aprovação humana.

## 6.6.3 — concluída
- Curadoria reativa e recalculo global idempotente.
- Fila acionável com motivos por questão.
- Correção de fonte primária e normalização de comentários.
- Dificuldade empírica reconstruída a partir das tentativas reais.
- Leituras derivadas não geram ruído no Cloud Sync.

A evolução funcional 6.7.0 — Tutor IA com scaffolding progressivo foi concluída.

## 6.6.4 — concluída
- Curadoria humana soberana sobre nota B quando os campos críticos estão íntegros.
- Separação entre qualidade editorial e conclusão da revisão.
- Fila distingue aprovação pendente de lacuna crítica.
- Conclusão explícita da revisão diretamente pela Curadoria.
- Hardening adicional de campos derivados no Cloud Sync.


## 6.6.5 — concluída

- Curadoria com conclusão humana explicitamente validada.
- Aprovação automática separada de revisão humana.
- Diagnóstico de bloqueios críticos diretamente no editor.
- Fluxo “salvar rascunho” versus “concluir e retirar da pendência” sem ambiguidade.

## 6.6.6 — concluída
- Navegação guiada das pendências de Curadoria para o campo exato do editor.
- Destaque visual, foco e orientação contextual por requisito.
- Fluxo de correção acionável tanto na fila quanto na inteligência individual da questão.

## 6.6.7 — concluída
- Validação contextual do enunciado.
- Remoção do limite mínimo fixo de 40 caracteres.
- Alertas de possível truncamento sem bloqueio automático da revisão humana.
- Preservação da navegação guiada e da Curadoria humana soberana.

## 6.6.8 — concluída

**Runtime Watchdog & Self-Healing**

- supervisor central como infraestrutura transversal, preservando exatamente seis motores;
- heartbeat e health checks de HTTP/UI, SQLite, event loop assíncrono, filas de tarefas, motores, Cloud Sync e Telegram;
- estados Healthy/Offline/Degraded/Suspect/Recovering/Failed e autorrecuperação limitada;
- ausência de internet tratada como offline normal;
- event loop dedicado para I/O com concorrência configurável e CPU/OCR mantidos em pool próprio;
- rate limiting thread-safe por token bucket para integrações externas críticas;
- histórico de tarefas bounded, journal JSONL rotativo e rotação do log de startup;
- painel de saúde e reinicialização manual de serviços recuperáveis;
- matriz de compatibilidade de Python 3.11–3.13, SQLite mínimo, schemas e dependências detectadas;
- nenhuma nova migração de banco.

A evolução **6.7.0 — Tutor IA com scaffolding progressivo + revisão multimodal** foi concluída.


## Próxima evolução após 6.7.0

- benchmark pedagógico do scaffolding (taxa de resolução por nível e efeito em revisões posteriores);
- experiência multimodal externa somente com opt-in explícito e provedor compatível;
- comparação de estratégias de pistas usando Questões Ouro pedagógicas;
- continuar sem substituir FSRS/KT/IRT por heurísticas de LLM.

## 6.7.1 — concluída

**Benchmark pedagógico + coleta de evidências acionável**

- “Coletar evidência” deixa de ser um chip passivo e abre um plano explicativo;
- abstenção é apresentada como falta de evidência, não como erro ou baixo domínio;
- candidatos diagnósticos são selecionados pelo mesmo conceito com informação IRT, prioridade e novidade;
- mini-simulado de coleta de evidência alimenta FSRS + KT + IRT e pode encerrar antecipadamente;
- benchmark cruza nível de scaffolding/representação com tentativas posteriores reais;
- retenção observada em janelas imediato/1d/3d/7d/30d;
- tendências somente com amostra mínima e ressalva explícita de associação observacional;
- sem nova migração; seis motores preservados.

## 6.7.2 — concluída

**Pesquisa Google para comentários editoriais**

- ação dedicada no editor para pesquisar a questão no Google Modo IA;
- preenchimento controlado de Explicação após a resposta;
- origem normalizada para IA assistida + revisão humana;
- código da questão como chave primária de pesquisa e enunciado como fallback;
- rascunho auditado, sem sobrescrever gabarito local e sem salvar automaticamente;
- Centro de Privacidade preservado e nenhum fallback silencioso para outro provedor.

## 6.7.3 — concluída

**Production Hardening / Build Reprodutível**

- lock exato de dependências e SHA-256 do lock com bloqueio de instalação em caso de adulteração;
- SBOM CycloneDX 1.5 e auditoria de vulnerabilidades via pip-audit quando disponível, com modo estrito para CI conectado;
- matriz automatizada de compatibilidade 3.11–3.13 e validação controlada/experimental em Python 3.14;
- atualizador seguro com validação de pacote, staging, proteção contra ZIP Slip, backup, quick_check, smoke test e rollback;
- política de backup/retenção diária, semanal e mensal com hashes, foreign_key_check e teste real de restauração;
- CI local/reprodutível por comando único, preservando exatamente os seis motores.

## 6.8.0 — concluída

**Multimodal RAG 3.0**

- opt-in explícito para envio de imagem/PDF a provedores externos;
- backends de recuperação `text`, `visual` e `hybrid`;
- grounding multimodal auditável no Knowledge Engine;
- pesquisa Google editorial endurecida com extração seletiva, estabilização de DOM e revisão humana;
- Centro de Privacidade preservado.

## 6.8.1 — concluída

**Benchmark Multimodal & Grounding Quality**

- benchmark determinístico sobre Questões Ouro locais;
- comparação dos backends textual, visual e híbrido;
- precisão/recall contra snapshots de fontes ouro quando disponíveis;
- cobertura de grounding, suporte ao comentário oficial, cobertura visual e segurança de caminhos locais;
- métrica de ganho híbrido contra o melhor backend isolado;
- painel acionável na Curadoria com aviso explícito de amostra insuficiente;
- nenhuma nova migração e exatamente seis motores preservados.

## 6.8.2 — concluída

**Reranking calibrado + regressão contínua de retrieval**

- reranking híbrido com pesos explícitos e features auditáveis;
- calibração determinística sobre Questões Ouro com grade fixa de perfis candidatos;
- comparação A/B offline e objetivo publicado (composite + recall + grounding);
- promoção do perfil apenas após confirmação humana;
- histórico versionado e rollback de configuração;
- baseline por release e matéria, com detecção de queda de score/recall/grounding;
- thresholds versionados e nenhuma alteração automática em FSRS/KT/IRT;
- Knowledge Engine 3.2 e exatamente seis motores preservados.

## 6.8.3 — concluída

**Retrieval Observability + Dataset de Regressão Expandido**

- histórico temporal de score, recall, grounding e cobertura por release/perfil;
- análise de drift de chunks/fontes por fingerprints locais, sem expor conteúdo ou caminhos;
- comparação entre releases e leitura por matéria;
- expansão assistida das Questões Ouro, sem autoaprovação e com confirmação humana individual;
- relatórios exportáveis em JSON/CSV para auditoria e comparação;
- Knowledge Engine 3.3 e exatamente seis motores preservados.
- **Hotfix de UX 6.8.3:** Benchmark RAG, Calibração e Observabilidade passam a ter atalhos sempre visíveis no topo de Revisar Banco; ações condicionais relevantes permanecem visíveis e desabilitadas com motivo quando não aplicáveis.

## 6.8.4 — concluída

**Retrieval Quality Gates + promoção segura de release**

- gates objetivos de score, recall, grounding e cobertura antes de promover uma release;
- quarentena automática quando regressões ultrapassam thresholds versionados;
- comparação com baseline aprovada e perfil de reranking ativo;
- promoção sempre humana, sem autoaprovação de release;
- override excepcional exige justificativa humana auditável;
- baseline de promoção separada da baseline de calibração;
- rollback restaura baseline e perfil de retrieval aprovados anteriormente;
- relatório exportável de aprovação/reprovação em JSON/CSV;
- Knowledge Engine 3.4 e exatamente seis motores preservados.

## 6.9.0 — concluída

**Mobile Integration Foundation**

- API mobile versionada e independente do schema interno do QuestFlow;
- modelo universal de eventos de aprendizagem (questão apresentada, resposta, mudança, envio, explicação, confiança, dificuldade e necessidade de estudo);
- identificação de usuário/dispositivo/sessão/tentativa e idempotência;
- sincronização offline-first com fila local e confirmação do servidor;
- projeção móvel mínima de questões, progresso e revisão, sem replicar a complexidade do desktop;
- autenticação/autorização próprias para cliente mobile;
- coexistência temporária Telegram + aplicativo durante homologação.

- identidade `account/tenant/learner` e controle local database-per-tenant;
- `exam_project_id`, `device_id`, `session_id`, `attempt_id` e `question_revision`;
- snapshots imutáveis de revisão para não reescrever o passado após edição de questão;
- pareamento temporário de uso único, QR local e revogação de aparelhos;
- Quality Gate de tempo ativo: wall-clock/inatividade ficam em auditoria e não contaminam métricas de velocidade;
- testes A/B de isolamento físico, idempotência e sincronização por cursor.

## 6.9.1 + QuestFlow Mobile 0.1 — concluída

**Alpha funcional iPhone/Android sobre a fundação 6.9.0**

- cliente React Native/Expo/TypeScript incluído em `mobile/`;
- telas Hoje, Questões, Progresso e Perfil;
- pareamento QR de uso único com descoberta do endereço local da Mobile API, sem credenciais administrativas;
- SQLite local como fonte operacional do cliente para cache/outbox/tentativas;
- sincronização offline-first com ACK idempotente e reprocessamento seguro de evento previamente persistido com erro;
- gabarito fora do cache anterior à tentativa e feedback somente após processamento da revisão apresentada;
- confiança coletada antes do resultado e dificuldade percebida opcional;
- sinal explícito “ainda tenho dúvida / preciso revisar”;
- cronômetro `client_active_timer_v1` que separa wall-clock/atividade/ociosidade e para após 60 s sem interação;
- background não acumula tempo ativo;
- push opt-in por dispositivo, revogação e limpeza local de sessão;
- Telegram permanece coexistindo durante homologação.

### Próxima evolução recomendada

**QuestFlow Mobile 0.2 — Cloud Gateway + Offline/Analytics ampliados**

- substituir dependência da LAN/Studio ligado por Gateway Cloud autenticado;
- OAuth/OIDC + PKCE e sessões multi-dispositivo reais;
- provisionamento/roteamento database-per-tenant no backend confiável;
- sync incremental cloud com resolução explícita de conflitos;
- lotes offline maiores e recuperação de sessão interrompida;
- gráficos móveis de evolução, memória, cobertura, erros e confiança × acerto;
- notificações de revisão e prioridade apoiadas em projeções, sem transportar conteúdo sensível no push;
- TestFlight/Google Play Internal Testing e telemetria técnica mínima.
