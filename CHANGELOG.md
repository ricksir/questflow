# QuestFlow Studio 6.24.0 + Mobile 0.16.0 — prioridades responsivas e roteiro de estudo

- Reorganiza as prioridades da Visão geral do Studio em uma grade responsiva, numerada e clicável, com até seis matérias visíveis e acesso filtrável à lista completa.
- Mantém o total de matérias coerente com a coleção real e abre o diagnóstico detalhado diretamente em cada cartão.
- Adiciona ao Mobile um roteiro visual de sessão em três etapas: recuperar, intercalar e consolidar, sempre alimentado pelos dados reais do estudante.
- Limita inicialmente o mapa de matérias no Mobile a cinco prioridades, informa o total e permite expandir ou recolher a lista quando o banco crescer.
- Reforça a quebra responsiva dos títulos e contadores do gráfico “Resultado por resposta”.
- Identifica inequivocamente os novos instaladores como Studio 6.24.0 e Mobile 0.16.0 (`versionCode` 22).
- Sem migração de banco; respostas, histórico, FSRS, KT, IRT, fila offline e pareamentos são preservados.

# QuestFlow Studio 6.23.2 + Mobile 0.15.6 — retomada segura após suspensão

- Detecta lacunas longas do agendador e do relógio como suspensão/hibernação do Windows, sem confundi-las com fechamento da janela.
- Aguarda até 45 segundos para o Chrome retomar o heartbeat antes de agir.
- Relança apenas a interface do Studio quando o Chrome não retorna, mantendo backend, Mobile LAN, outbox e serviços internos ativos.
- Registra `suspend_resume_detected`, `interface_resumed` e tentativas de relançamento em `data/runtime_lifecycle.jsonl` com rotação limitada.
- Mantém o fechamento explícito e o fechamento normal da janela com checkpoint SQLite seguro.
- Adiciona ao Manager opções visíveis para ativar ou remover a inicialização automática do Studio com o Windows.
- Mantém o Mobile 0.15.6 e o mesmo contrato `/api/v1/mobile`; não exige novo APK.

# QuestFlow Studio 6.23.1 + Mobile 0.15.6 — feedback rápido e rotação entre blocos

- Persiste a tentativa e devolve acerto/erro antes da reconstrução de FSRS/KT/IRT e analytics.
- Processa projeções pesadas em fila durável, retomável e transacional no runtime do Studio.
- Remove sincronizações completas do caminho de avanço entre questões e promove microlotes pré-carregados.
- Impede questões do bloco anterior em novas sessões recomendadas ou por matéria, preservando os modos explícitos Revisões e Erros.
- Aplica a mesma proteção de rotação à Reserva Offline e ao cache local do Mobile.

# QuestFlow Studio 6.23.0 + Mobile 0.15.5 — arquitetura modular e catálogo externo

- Adota monólito modular hexagonal com módulos verticais, registro extensível e propriedade explícita de todas as tabelas no SQLite.
- Adiciona eventos internos duráveis ligados à outbox existente, event store seletivo e catálogo de projeções reconstruíveis FSRS/KT/IRT/analytics.
- Introduz contratos `questflow.studio.v1` e frontend TypeScript carregado por rota, preservando o RPC legado durante a migração.
- Permite selecionar a APIdasQuestões como catálogo do Studio, com API Key protegida por DPAPI e normalização para o formato QuestFlow; Mobile permanece compatível e isolado da credencial.

# QuestFlow Studio 6.22.16 + Mobile 0.15.5 — feedback imediato e layout responsivo

- Remove os textos residuais do Mobile 0.14.0 no Studio e centraliza a versão exibida em `0.15.5`.
- Corrige o enquadramento do resumo “Resultado por resposta”, exibindo variação completa sem corte.
- Reordena as ações da questão: Continuar, Pular Questão, Assunto ainda não Estudado e CORRIGIR QUESTÃO.
- Registra a resposta e recebe o feedback na mesma requisição; bootstrap e reserva offline atualizam em segundo plano.
- Sem migração de banco; o protocolo mantém compatibilidade com os clientes anteriores.

# QuestFlow Studio 6.22.15 + Mobile 0.15.4 — prioridades escaláveis

- O total contabiliza todas as matérias em foco, sem depender do limite visual do resumo.
- O cartão mostra as quatro maiores prioridades e informa `+N outras prioridades` quando necessário.
- **Ver todas** abre uma lista completa, ordenada pelo score, com busca por matéria e filtro de prioridade alta/média.
- Cada linha abre o diagnóstico detalhado da respectiva matéria.
- Sem migração de banco e sem alteração no APK Mobile 0.15.4/build 19.

# QuestFlow Studio 6.22.14 + Mobile 0.15.4 — prioridade por matéria consistente

- Corrige a divergência em que o painel informava quatro matérias em foco, mas limitava a renderização a três.
- O cabeçalho agora é calculado a partir da mesma coleção efetivamente exibida.
- A quarta matéria recebe cor de apoio própria e permanece acessível por texto e percentual.
- Sem migração de banco e sem alteração no APK Mobile 0.15.4/build 19.

# QuestFlow Studio 6.22.11 + Mobile 0.15.2 — pareamento compacto e lembretes locais

- O pareamento passa a destacar a leitura do QR e recolhe endereço e token na alternativa manual.
- Os lembretes são agendados no próprio Android e deixam de depender de Firebase/FCM.
- Erros nativos de configuração não são mais expostos na interface; o usuário recebe orientação curta e segura.
- O lembrete diário continua funcionando sem internet e com o Studio fechado.
- Mobile identificado como `0.15.2` (`versionCode 17`) e Studio como `6.22.11`.
- Banco, respostas, histórico, sessão e fila offline são preservados.

# QuestFlow Studio 6.22.10 — correção responsiva do banco agrupado

- Impede que títulos longos e tabelas ampliem o grupo além da largura útil da página.
- Mantém contadores e o botão **Organizar aula** dentro da tela, com quebra responsiva do cabeçalho.
- A tabela usa colunas proporcionais, quebra de texto e rolagem horizontal somente dentro da sua própria região.
- As ações `Corrigir`, `Editor completo` e `Excluir` passam a quebrar dentro da coluna, sem empurrar a interface.
- Pacote incremental somente do Studio; Mobile 0.15.1, banco local e histórico são preservados.

# QuestFlow Studio 6.22.9 — catálogo canônico de matérias e aulas

- A aba **Corrigir banco** agora agrupa as questões em **Matéria → Aula**.
- `Aula 0`, `Aula 00` e `00` são reconhecidas como o mesmo grupo numérico.
- Cada aula pode receber matéria, número e título canônico sem apagar o assunto individual das questões.
- A correção é aplicada em lote, preservando UID, respostas, histórico, PDF e página.
- O catálogo registra aliases e normaliza automaticamente importações futuras.
- As colunas visíveis **PDF origem** e **Pág.** foram removidas da visão agrupada.
- Migração SQLite aditiva `question_bank/9`; Mobile permanece em `0.15.1`.

# QuestFlow Studio 6.22.8 — Markdown editorial e alternativas sem pontuação

- Reconhece números de questão envolvidos por negrito, destaque HTML e títulos do Markdown gerado pelo pipeline.
- Separa corretamente `Comentários` e `Gabarito` mesmo quando os rótulos também estão formatados em Markdown.
- Interpreta alternativas editoriais no formato `A texto`, inclusive quando várias opções são agrupadas na mesma linha.
- Impede que “Julgue os itens” transforme questões com alternativas explícitas em Certo/Errado.
- Remove marcação estrutural dos campos finais e preserva páginas com tabelas ou figuras para revisão.
- Validado com 51 questões reais dos dois cadernos `contabilidade_aula02`.
- Pacote incremental somente do Studio; Mobile 0.15.1, banco local e histórico são preservados.

# QuestFlow Studio 6.22.7 — cadernos de Questões Comentadas

- Reconhece cadernos cujo cabeçalho usa `QUESTÕES COMENTADAS`, sem exigir a palavra `RESOLVIDAS`.
- Converte cada bloco `Comentários` integralmente para a explicação pós-resposta e separa o gabarito.
- Corrige a classificação que confundia `atributo` com `tributo`, preservando a matéria Fluência em Dados.
- Mantém questões com alternativas gráficas, extrai a página de apoio e as encaminha para revisão humana.
- Validado com 68 questões reais de `fluenciaemdados.pdf`, todas com gabarito e explicação.
- Pacote incremental somente do Studio; Mobile 0.15.1, banco local e histórico são preservados.

# QuestFlow Studio 6.22.6 — sincronização idempotente do catálogo

- Corrige a comparação entre durações equivalentes como `1h30` e `01:30`, que fazia cada verificação da planilha parecer uma alteração nova.
- Impede que atualizar ou focar novamente o painel recrie centenas de eventos do catálogo após uma sincronização concluída.
- Alterações reais de progresso agora enfileiram somente as aulas afetadas, sem desativar e reativar todo o catálogo.
- Mantém a verificação automática da planilha, mas transforma snapshots idênticos em operação sem escrita e sem novo histórico de importação.
- Pacote incremental somente do Studio; Mobile 0.15.1, banco local e histórico são preservados.

# QuestFlow Studio 6.22.5 — Comentário integral como explicação

- Formaliza o fluxo obrigatório `PDF → Markdown paginado → campos estruturados` antes da gravação no banco.
- Mapeia todo o conteúdo abaixo de `Comentário` ou `Comentários` para o campo `explicacao` da questão.
- Usa a declaração de gabarito para preencher `gabarito`, sem misturá-la à explicação.
- Preserva trechos explicativos que aparecem depois da declaração do gabarito, incluindo comentários das demais alternativas.
- Validado com 50 questões reais dos três cadernos `auditoria_aula03`.
- Pacote incremental somente do Studio; Mobile 0.15.1, banco local e histórico são preservados.

# QuestFlow Studio 6.22.4 — OCR de cadernos vetoriais digitalizados

- Reconhece PDFs sem camada de texto cujas letras foram convertidas em milhares de vetores pelo PDFium.
- Ativa OCR paginado para cadernos `QUESTÕES RESOLVIDAS E COMENTADAS` antes do extrator visual legado do QConcursos.
- Corrige a implementação ausente do OCR de PDFs no pipeline Markdown.
- Interpreta gabaritos em frases como `Pelo exposto, nosso gabarito é a letra A` e opções agrupadas na mesma linha.
- Evita colisões de código quando a numeração recomeça dentro do mesmo arquivo.
- Preserva a página original para questões que dependem de tabela, figura ou diagrama e as envia para revisão humana.
- Validado com 50 questões reais dos três anexos `auditoria_aula03`.
- Pacote incremental somente do Studio; Mobile 0.15.1, banco local e histórico são preservados.

# QuestFlow Studio 6.22.3 — importação de questões resolvidas e comentadas

- Reconhece PDFs com cabeçalho `QUESTÕES RESOLVIDAS E COMENTADAS` e gabarito inserido após o comentário de cada questão.
- Separa enunciado, cinco alternativas, gabarito e explicação sem importar o comentário como parte da questão.
- Uma extração com zero questões passa a falhar de forma explícita, em vez de exibir `Concluído 100%`.
- O botão de processamento permanece desabilitado depois que a fila é concluída e limpa, evitando o alerta contraditório de arquivo inválido.
- Pacote incremental somente do Studio; Mobile 0.15.1, banco local e histórico são preservados.

# QuestFlow Studio 6.22.2 — correção da versão fonte do Mobile

- Corrige o cartão `Versão fonte` do Studio para exibir o Mobile corrente `0.15.1`.
- Remove o literal legado `0.14.0` e sincroniza o rótulo com a versão declarada pelo release visual.
- Pacote incremental somente do Studio; Mobile 0.15.1 e banco local são preservados.

# QuestFlow Studio 6.22.1 — histórico real desde a primeira resposta

- Painel Visual e Mobile usam `telegram_attempts` desde a primeira resposta, com pontos brutos de acerto/erro e linha acumulada.
- A interface substitui `n=24` por linguagem direta como `24 respostas`.
- O histórico completo é o recorte padrão; filtros recentes permanecem opcionais.
- A cobertura das fontes em Geração e Legislação deixa de ser sticky e não sobrepõe os painéis seguintes durante a rolagem.

# QuestFlow Studio 6.21.1 — evidência progressiva e eliminação de colunas fantasmas

- Painel visual passa a mostrar linha de base desde a primeira janela real, direção inicial com duas janelas, tendência emergente entre quatro e sete e tendência consolidada a partir de oito.
- Evolução temporal consolidada deixa de reservar um cartão vazio quando há uma única janela respondida.
- Volume por janela, tamanho da amostra, diferença recente e nível de confiança ficam visíveis sem fabricar histórico.
- Geração e legislação recebe rail de cobertura/quality gates e a legislação volta a ocupar toda a largura útil.
- Fluxo Telegram recebe pulso operacional baseado exclusivamente nos eventos visíveis do histórico.
- Configurações recebe painel complementar de escopo, validação e segurança; categorias inativas continuam `hidden` e `inert`.
- Mobile permanece em 0.14.0 e é preservado por esta atualização; banco e histórico não sofrem migração destrutiva.

# QuestFlow Studio 6.18.1

## 6.18.2 — Hotfix de inicialização da interface Web

- Restaura as funções de documentação/cobertura de trilhas removidas acidentalmente na 6.18.1.
- Corrige falha JavaScript durante `bindEvents()` que impedia o heartbeat da interface e fazia o Studio ficar em “Carregando/Preparando interface”.
- Mantém intactas as mudanças da 6.18.1 em Correções e Matérias não Estudadas.
- Adiciona teste estático de contrato para símbolos críticos chamados durante o startup da Web UI.


- Renomeia Correções para **Correções e Matérias não Estudadas**.
- Separa pendências editoriais e conteúdos ainda não estudados em áreas independentes.
- Mantém compatibilidade da API `list_corrections` e adiciona projeções separadas.
- Mobile 0.13.1: resumo offline mostra respostas contabilizadas e resultados aguardando correção, sem traço ambíguo.
- Sem alteração no Learning Engine, FSRS, KT, IRT ou Cloud Sync.

# QuestFlow Studio 6.18.0 + Mobile 0.13.0 — Revisão de Erros e Reserva Offline estrita

- Tutor IA: **Erros recentes** vira **Revisão de Erros com o Tutor IA**, uma fila de trabalho real.
- Ao aprovar a orientação do Tutor, o erro mais recente da questão sai da fila e entra em **Erros Tratados**.
- Se a mesma questão for respondida incorretamente novamente depois do tratamento, ela retorna automaticamente à fila.
- Reserva Offline: uma questão nunca respondida pode ser reservada; uma questão já respondida só volta quando o vencimento de espaçamento calculado pelo Studio estiver efetivamente devido.
- A Reserva Offline não usa antecipação, correção manual ou lógica local do Mobile para reapresentar item já respondido; FSRS/fallback de espaçamento do Studio permanece autoridade.
- Mobile: resposta offline deixa de exibir spinner persistente de feedback; a tela informa que a resposta está salva localmente e que não há conexão em andamento.
- Mobile: alternativas eliminadas por swipe ficam visualmente mais fortes, com borda/fundo de eliminação, texto riscado em destaque e marcador **ALTERNATIVA ELIMINADA**.
- Nenhuma alteração no gabarito offline, KT, IRT, Learner Model ou prioridade adaptativa local.

# QuestFlow Studio 6.17.1 — Tutor IA editável e sincronizado com a questão atual

- Rascunhos do Tutor IA agora são editáveis pelo usuário sem apagar o texto original gerado pela IA.
- Cada edição humana é versionada e auditada; ao salvar, a avaliação independente é recalculada e o status retorna a rascunho.
- Interações do Tutor registram snapshot/hash da questão usada na geração.
- Alterações posteriores em Revisar banco tornam orientações anteriores desatualizadas, bloqueiam aprovação e oferecem regeneração com a questão atual.
- O Workspace recupera a interação mais recente da questão ao voltar para o Tutor, evitando manter um DOM antigo sem contexto.
- Auditoria diferencia texto original da IA, versão humana e questão-base alterada.
- Mobile permanece 0.12.0; sem alteração no Learning Engine, FSRS, KT, IRT ou Reserva Offline.

# QuestFlow Studio 6.17.0 + Mobile 0.12.0 — histórico offline e interface Mobile limpa

- Mobile: cria a área **Respondidas offline**, independente da questão atualmente aberta, com situação, resposta marcada, gabarito, resultado e explicação após a reconciliação com o Studio.
- Sincronização: percorre todas as tentativas offline ainda sem feedback, consulta o resultado oficial do Studio e grava o retorno localmente; não limita a correção à tentativa corrente.
- Compatibilidade: tenta recuperar também tentativas da 0.11.x que ficaram com alternativa marcada e sem feedback, classificando-as para reconciliação posterior.
- Learning Engine permanece centralizado no Studio: o Mobile não calcula gabarito, FSRS, KT, IRT ou prioridade pedagógica; apenas apresenta o feedback oficial após sincronização.
- UX Mobile: mantém Fast Refresh em desenvolvimento, mas suprime o banner visual `Refreshing...`; Preview/Production não exibem esse chrome de desenvolvimento.
- Dev Client: `toolsButton=false`, onboarding/menu automático desativados. Para remover o botão flutuante já embutido em um APK antigo é necessária nova build nativa 0.12.0.
- Entrega dois perfis EAS: **Preview** para uso diário/offline sem overlays de desenvolvimento e **Development** para um Dev Client 0.12.0 com interface limpa.
- Atualizador Mobile preserva `node_modules`, `.expo`, `android`, `ios` e cria backup das fontes antes da cópia; em falha de typecheck restaura as fontes anteriores.
- Nenhuma migração destrutiva do SQLite do Studio e nenhuma alteração na política adaptativa da Reserva Offline.

# QuestFlow Studio 6.16.1 — Tutor IA com seleção humana de questões

- Corrige o seletor **Questão para analisar**, que podia exibir UUIDs internos no lugar do código da questão.
- O backend do Tutor passa a entregar um view-model explícito: UID apenas interno; código, matéria, assunto, aula e trecho do enunciado para apresentação.
- O seletor mostra **Código → Matéria → Assunto/Aula → início do enunciado**, sem fallback visual para UUID.
- Adiciona busca por código, matéria, assunto, aula ou palavras do enunciado para reduzir a carga cognitiva ao localizar uma questão.
- A microcopy explica a intenção pedagógica: escolher a questão que o usuário quer entender; o Tutor usa o histórico para diagnosticar a provável causa do erro e orientar a revisão.
- Mobile permanece 0.11.0; nenhuma alteração de banco, Learning Engine, Reserva Offline ou Cloud Sync.

# QuestFlow Studio 6.16.0 + Mobile 0.11.0

- Mobile: gesto horizontal em alternativas para riscar/desriscar opções durante a resolução, sem registrar isso como evidência pedagógica.
- Mobile: Reserva Offline planejada pelo Studio/Learning Engine e renovada a cada sincronização.
- Mobile: permite continuar respondendo questões sem internet e sem Studio disponível; respostas ficam na outbox local e são corrigidas/reprocessadas pelo Studio quando a conexão retorna.
- Segurança pedagógica: o Mobile continua Study Only. A seleção vem de AdaptiveSessionOrchestrator -> StudyBatchService -> StudyRepository/Learning Engine; a Reserva Offline é apenas um snapshot ordenado dessa decisão e não se readapta localmente.
- Privacidade/gabarito: a Reserva Offline não armazena gabarito nem explicação corretiva; o resultado é obtido após sincronização.
- Studio Mobile API: /api/v1/mobile/sync pode devolver offline_study_pack após aplicar os eventos enviados pelo aparelho, garantindo que a nova reserva seja recalculada com a evidência mais recente.
- Mobile 0.11.0 não adiciona dependências nativas. Atualização de código preserva node_modules e .expo.

# QuestFlow 6.15.2 — Hotfix de primeira abertura após atualização

- Corrige a condição de corrida em que a primeira abertura após um UPDATE podia encontrar o Google Chrome, mas não receber heartbeat da interface.
- O Manager agora encerra explicitamente apenas o Chrome que usa o perfil privado `data\chrome_runtime_5_4_0`; sessões normais do Chrome não são encerradas.
- O runtime confirma que o servidor local está aceitando conexões antes de abrir a interface.
- O runtime remove Chrome órfão do perfil QuestFlow e faz uma segunda tentativa automática antes de mostrar erro.
- Nenhuma alteração de banco, Course Catalog, Learner State, Mobile ou Cloud Sync.

# QuestFlow 6.15.1 — Hotfix Estudos e Trilhas na interface Web

- Corrige a ausência do painel **Estudos e Trilhas / Planilha de estudos e trilhas** na interface Web principal usada pelo Studio.
- Adiciona status da fonte ativa, faixa de trilhas, abas detectadas, versão do catálogo e última sincronização.
- Adiciona **Testar planilha** com dry-run somente leitura antes de qualquer alteração.
- Adiciona **Trocar/Atualizar planilha** com backup, mesclagem segura e relatório pós-operação.
- Expõe conflitos de correspondência para decisão humana; a mesclagem fica bloqueada enquanto houver conflito não resolvido.
- Mantém o núcleo Course Catalog / Learner State da 6.15.0 e o Mobile 0.10.1 sem alteração.

# QuestFlow 6.15.0 — Course Catalog Safe Merge

- Separa a planilha de trilhas em **Course Catalog** (estrutura atual do curso) e **Learner State** durável no SQLite, sem criar um Learning Engine paralelo.
- Adiciona preflight/dry-run no Studio, comparação detalhada, detecção de aulas novas/alteradas/arquivadas e resolução humana de correspondências incertas.
- Implementa identidade estável de aula sem depender da linha da planilha e mesclagem incremental em que célula pessoal vazia **nunca apaga progresso conhecido**.
- Antes da aplicação, cria backup SQLite validado por SHA-256, `PRAGMA quick_check` e `foreign_key_check`; falhas posteriores restauram banco, taxonomia e URL anterior.
- `studied_scope` passa a ser aditivo/durável: trocar para uma planilha com células vazias não faz o QuestFlow esquecer assuntos já estudados.
- Cloud Sync separa eventos de catálogo em `content.*` e Learner State em `learner.*`; o estado pessoal do catálogo usa merge monotônico em vez de `last-write-wins` cego.
- Mantém compatibilidade com `MAPA_AF`/`MAPA_AT`/`MAPA` e `CICLO_REG`/`CICLO`, e mantém `taxonomy_spreadsheet_url` para compatibilidade, mas a troca oficial ocorre pela interface segura.
- Mobile permanece em **0.10.1** e continua Study Only; nenhuma informação sobre URL, planilha, dry-run ou diagnóstico estrutural é exposta ao aplicativo.

## 6.14.4

- Corrige o loop de **Retomar primeira sincronização** que podia manter a fila inalterada quando `RECOVERY_GUARD.json` ainda estava ativo após uma recuperação de dados.
- A própria **Ativação segura** passa a ser a reconciliação humana explícita esperada pelo Recovery Guard: somente após backup SQLite validado o guard é arquivado com SHA-256 e removido da posição ativa.
- O automático continua bloqueado pelo estado da ativação até `fila = 0` e `conflitos = 0`, mesmo depois da liberação auditada do guard.
- `sync_until_idle()` passa a propagar bloqueios/disabled como erro acionável em vez de retornar um ciclo sem progresso silencioso.
- A UI deixa de dizer que a sincronização "avançou" quando nenhum evento foi efetivamente enviado e mostra a etapa **Proteção pós-recuperação** no preflight quando aplicável.
- Mantém a retomada idempotente da 6.14.3 e o Mobile 0.10.1 sem alterações.

## 6.14.3

- Corrige a ativação inicial do Cloud Sync para filas maiores que 2.500 eventos; a 6.14.2 usava 10 rodadas × 250 eventos e podia encerrar uma primeira sincronização grande antes de esvaziar a fila.
- A primeira sincronização passa a avançar em blocos retomáveis, mantendo o automático desligado até fila = 0 e conflitos = 0.
- Uma ativação parcial pode ser retomada sem executar nova semeadura completa e sem gerar novos event IDs para linhas já preparadas.
- A interface mostra a quantidade restante entre blocos e oferece **Retomar primeira sincronização** em vez de exibir apenas uma falha genérica.
- Mantém idempotência de retentativas, backup pré-escrita e proteção de conflitos.

## 6.14.2

- Mobile 0.10.1: conteúdos marcados como **Assunto ainda não estudado** continuam sem contar como tentativa, acerto ou erro, mas passam a aparecer também no Studio > **Correções**.
- A aba Correções passa a separar visualmente correções editoriais de pendências pedagógicas e exibe contadores próprios.
- Cada pendência **Ainda não estudado** abre uma janela com questão de origem, matéria, assunto, aula, datas, quantidade de marcações e orientação sobre o que fazer.
- O Studio permite abrir a questão no banco, marcar o conteúdo como estudado ou remover explicitamente a marcação.
- Marcar como estudado libera novamente o assunto para futuras sessões adaptativas; remover a marcação exige confirmação porque também libera o assunto sem declarar que houve estudo.
- O badge global de Correções passa a contabilizar correções editoriais + conteúdos ainda não estudados.
- Mobile 0.10.1 fixa fundo/status bar ao tema escuro desde a raiz e configura a StatusBar Android como não translúcida para reduzir o flicker azul transitório observado na parte superior.
- Nenhuma regra FSRS/KT/IRT é alterada por uma marcação de assunto ainda não estudado.

## 6.14.1 — Cloud Sync Safe Activation

- Introduz ativação segura do Cloud Sync com preflight, comparação por IDs/hashes, dry-run, backup validado e liberação do automático somente após primeira sincronização íntegra.
- Preserva Mobile 0.10.0 sem expor Turso, Cloud Sync ou diagnóstico técnico ao aplicativo.

## 6.14.0


- Introduz `AdaptiveSessionOrchestrator` sobre o `StudyBatchService`, sem criar um motor pedagógico paralelo.
- Mobile 0.10.0 passa a consumir micro-lotes adaptativos de 3 questões e recebe replanejamento entre micro-lotes após novas evidências.
- Implementa prefetch do próximo micro-lote, invalidação segura de prefetch quando há misconception/lacuna relevante e fallback offline por micro-lotes.
- Formaliza a matriz acerto × confiança: erro com alta confiança vira candidato a misconception; acerto incerto favorece transferência conceitual.
- Reforça anti-loop por questão e por conceito, interleaving por matéria/assunto/aula e substituição de itens retirados antes da resposta.
- Acrescenta tempo esperado contextual à decisão adaptativa, sem converter rapidez isolada em evidência de domínio.
- Cada sessão recebe objetivo pedagógico explícito e pode mudar entre perfis `balanced`, `consolidate`, `transfer` e `expand`.
- Cria persistência de sessões, micro-lotes e decisões adaptativas, com auditoria completa e painel Studio **Por que esta questão?**.
- Cloud Bridge 0.5 oferece micro-lotes em modo cached/offline, sem fingir que recalcula FSRS/KT/IRT fora do Studio.
- Instrumenta a comparação futura por retenção atrasada/domínio; acurácia imediata permanece apenas métrica descritiva.
- Mantém o Mobile exclusivamente voltado ao estudo; arquitetura, serviços e explicabilidade técnica ficam no Studio.

## 6.13.0 — StudyBatchService centralizado

- Cria `StudyBatchService` como camada única de composição de sessões sobre `StudyRepository.select_questions`; o Mobile deixa de manter ranking pedagógico próprio.
- Modo Recomendado passa a combinar revisões FSRS vencidas, itens novos, lacunas de domínio e transferência de conceito, preservando correções/relearning críticos.
- Adiciona `recent_exposure_guard` com proteção da primeira questão entre sessões e penalidade de repetição para itens apresentados recentemente, inclusive questões puladas.
- Adiciona interleaving por matéria, assunto e aula dentro do lote sem quebrar a precedência do motor adaptativo central.
- Corrige a classificação FSRS inicial: ausência de histórico não é mais tratada como baixa performance; primeira resposta correta não vira `Hard` apenas por prior_accuracy=0,50.
- Baixa/média confiança passa a favorecer outra questão do mesmo conceito; o Mobile também reordena o restante do lote quando já existe um item de transferência compatível.
- Cache offline evolui de um único lote para pool rotativo de até 120 questões, evitando reiniciar sempre com o mesmo conjunto quando houver alternativas armazenadas.
- Cada questão recebida pelo Mobile carrega metadados auditáveis de seleção (`policy`, `bucket`, `reason`, `recent_exposure_penalty`, `topic_transfer`, `core_rank`).
- Mantém a fronteira Mobile Study Only: Telegram, saúde da IA, serviços, arquitetura e diagnósticos permanecem exclusivamente no Studio.
- Mobile atualizado para 0.9.0 sem novas dependências nativas.

## 6.12.2 — Telegram somente no Studio

- Remove completamente Telegram da superfície de produto do Mobile: tela, contexto React, cliente API, tipos e contrato JSON.
- Remove `/api/v1/mobile/channels/telegram`; pausar/retomar questões pelo Telegram permanece exclusivamente no Studio.
- Retira `channels` de Bootstrap/Today/Progress e retira o campo `channel` do histórico recente entregue ao celular.
- Mantém todos os eventos de estudo agregados nas métricas pedagógicas, independentemente da origem, sem expor o canal ao aluno.
- Desacopla `MobileFoundationService` dos callbacks de estado/controle do Telegram no composition root.
- Mobile atualizado para 0.8.2 sem dependências nativas novas.

## 6.12.1 — Mobile Study Only

- Reverte a exposição de Saúde da IA ao Mobile e fixa a fronteira de produto: o aplicativo fica dedicado ao estudo.
- Remove a tela `Saúde da IA`, o endpoint `/api/v1/mobile/ai-health`, a projeção técnica do Cloud Bridge e o tipo/API correspondente no cliente Expo.
- O Mobile deixa de exibir versão, endpoint, rota ativa, cursor, Cloud Bridge, diagnóstico técnico e indicadores de infraestrutura.
- Perfil Mobile passa a destacar projeto, revisões do dia, questões sugeridas, respostas ainda não salvas, lembretes e controle do envio de questões pelo Telegram.
- Saúde da IA, Retrieval Health, Quality Gates, Watchdog, serviços, arquitetura, sincronismo técnico e diagnósticos permanecem exclusivamente no Studio.
- O Cloud Gateway remove projeções legadas `ai_health` quando recebe uma nova publicação do tenant.
- Mobile atualizado para 0.8.1 sem dependências nativas novas.

## 6.12.0 — Saúde da IA exposta ao Mobile (substituída pela 6.12.1)


- Expõe Saúde da IA ao Mobile por contrato read-only `questflow.mobile.ai_health.v1`.
- Mantém a projeção técnica separada de acurácia, mastery, FSRS, memória e demais métricas pedagógicas do learner.
- Adiciona `GET /api/v1/mobile/ai-health` no Studio e no Mobile Cloud Gateway.
- Publica a mesma projeção técnica no Cloud Bridge, sem comandos de reavaliação, promoção, override ou rollback.
- Mobile 0.8.0 recebe tela dedicada Saúde da IA acessível por Perfil > Sistema, fora das telas de desempenho.
- Mantém `null` para Score/Recall/Grounding quando a amostra Ouro não permite avaliação.

## 6.11.0 — Retrieval Health Service isolado

- Separa Observabilidade e Quality Gates completamente do AI Engine no caminho de aplicação.
- Introduz `RetrievalHealthService` como serviço transversal dedicado, sem transformá-lo em um sétimo motor pedagógico.
- Implementa CQRS local: consultas leem somente o Metrics Snapshot Store; benchmark e fingerprint do índice rodam apenas por comando explícito.
- Adiciona Evaluator Worker serial dedicado, impedindo avaliações concorrentes e reduzindo contenção de CPU/SQLite.
- Uma única avaliação produz o snapshot usado simultaneamente por Observabilidade e Quality Gates, eliminando métricas divergentes e benchmark duplicado.
- Promoção e override passam a usar exclusivamente o último Quality Gate persistido; ações administrativas não executam benchmark implicitamente.
- Adiciona contrato `questflow.retrieval_health_contract.v1`, snapshot canônico e estado persistido de jobs com recuperação segura após interrupção.
- Integra o novo serviço ao Watchdog como infraestrutura não crítica e à visão de arquitetura como `services`, preservando os seis motores existentes.
- Studio acompanha progresso do Evaluator Worker por polling; Mobile 0.7.3 permanece sem alteração e não recalcula métricas de retrieval.

## 6.10.3 — Retrieval read-only e correção visual incremental

- Remove blur de tela inteira e animação por escala nos modais para reduzir flicker/artefatos do compositor Chrome/GPU no Windows.
- Desativa o blur da topbar enquanto um modal está aberto e adiciona instrumentação local de pageshow, visibility e long tasks.
- Observabilidade passa a abrir em modo somente leitura, mostrando o último snapshot sem executar benchmark ou gravar estado.
- Quality Gates passam a abrir o último estado salvo; benchmark só roda ao clicar em **Reavaliar gates**.
- Ausência de Questões Ouro deixa de ser representada como qualidade 0.0; métricas sem amostra usam `null`/“Não avaliada”.
- Versões de QuestFlow e Knowledge Engine deixam de ser hardcoded nas telas de retrieval.
- Detalhes técnicos e ações administrativas ficam progressivamente revelados por “Mostrar detalhes”/“Modo avançado”.
- Mobile permanece em 0.7.3; contrato semântico de métricas é preservado para evitar interpretação divergente entre Studio e aplicativo.

## 6.10.2 HOTFIX — Atualização Windows / caminhos longos
- Corrige a falha do atualizador seguro no Windows ao extrair dependências Mobile com caminhos que atingiam o limite legado de 260 caracteres.
- Pacotes de atualização deixam de transportar `mobile/node_modules`, `.expo`, builds temporários e a pasta `data`; essas áreas são preservadas localmente pelo Manager.
- O extrator seguro passa a ignorar caches/dependências transitórias mesmo se um pacote futuro as incluir por engano.
- O atualizador externo passa a preferir o `questflow_update_runner.py` da instalação atual, evitando continuar preso a um runner antigo em `%LOCALAPPDATA%\QFS`.
- Mantém integralmente as melhorias visuais do Studio 6.10.1 e o QuestFlow Mobile 0.7.3.

## 6.10.1 + QuestFlow Mobile 0.7.3 — Hierarquia visual e resumo de tempo
- Corrige o bloco de tempo no resumo da sessão Mobile para não cortar textos em telas estreitas ou com fonte ampliada.
- Duração do resumo passa a usar formato compacto e ajuste automático de fonte, preservando a explicação pedagógica do que entra no tempo ativo.
- Tempo ativo médio na aba Progresso também usa duração compacta para evitar estouro de layout.
- Todos os painéis principais do Studio passam a ter faixa lateral, cabeçalho tonal e fundo suave alternado para separar visualmente cada bloco durante a rolagem.
- Configurações ganha identidade de cor estável para Rede, Cloud Sync, IA, monitor de atualizações, Watchdog e zona de risco.
- Seções internas do editor de questões recebem a mesma hierarquia visual, com cores de destaque próprias.
- Corrige tipagens TypeScript já presentes no pacote para permitir `npm run typecheck` integral no Mobile.

## 6.10.0 HOTFIX7 - Manager V2.6 / Windows SQLite handle safety
- Fecha explicitamente conexões SQLite do quick_check e backup para evitar WinError 32 no Windows.
- Torna o teste de restauração tolerante a atraso transitório de liberação de arquivo temporário.
- Motor externo V2.6 aplica o patch mesmo partindo de uma instalação 6.9.8.
- Mantém exclusão de caches/runtimes transitórios do backup.

## 6.10.0 HOTFIX6 — Manager V2.5
- Corrige WinError 32 no teste de restauração ao excluir `data/chrome_runtime_*` e perfis de navegador dos backups persistentes.
- Adiciona runner externo do atualizador em `%LOCALAPPDATA%\QFS\updater`.
- Mantém banco, configurações, credenciais e dados pedagógicos protegidos.

## 6.10.0 HOTFIX3 - Manager V2.2
- Remove dependência de Expand-Archive no updater externo do Windows.
- Atualização passa a usar diretamente o mecanismo Python instalado, preservando dependências Mobile fora da troca de código.

## 6.10.0 HOTFIX1 - Manager V2
- Atualizador passa a rodar fora da pasta instalada.
- Nova janela de progresso evita a falsa impressao de travamento apos a confirmacao.
- Logs permanentes em `%LOCALAPPDATA%\QFS\logs`.
- `QUESTFLOW.bat` deixa de fechar silenciosamente em caso de erro do Manager.
- Incluido `REPARAR_QUESTFLOW_MANAGER.bat`, que corrige o Manager sem tocar em `data`.

## 6.10.0 - Mobile Study Session
- Nova tela de criação de sessão com modos Recomendado, Revisões, Meus erros e Por matéria.
- Lotes de 5, 10, 15 ou 20 questões.
- Retomada local de sessões interrompidas.
- Resumo final com acertos, erros, puladas, acurácia e tempo ativo.
- API Mobile ganhou filtros seguros de sessão e indicadores de revisão/erro sem exposição de gabarito.
- Cloud Bridge opcional mantém compatibilidade com filtros disponíveis no pacote offline.

## 6.9.9 - Mobile Professional UX
- Corrige safe area inferior no Android e impede sobreposição da barra do sistema sobre as abas.
- Redesenha Hoje, Questões, Progresso e Perfil com design system mais consistente e colorido.
- Substitui o bloco Telegram da tela Hoje por desempenho visual (acertos/erros e barras por matéria).
- Cria a aba lateral QuestFlow Mobile no Studio para pareamento, aparelhos, acesso LAN e diagnóstico.
- Move Cloud Bridge para área opcional/experimental do Mobile.
- Mantém cronômetro contando somente com a aba Questões em foco e exibição humana de duração.
- Recovery Guard do Cloud Sync torna-se seguro também para serviços/test doubles sem `database_path`, preservando o heartbeat do watchdog.

## 6.9.8 HOTFIX1 - Easy Update Manager
- Novo `QUESTFLOW.bat` como ponto único para iniciar Studio/Mobile, atualizar e diagnosticar.
- Novo `INSTALAR_QUESTFLOW_FACIL.bat` para migração inicial para `%USERPROFILE%\QuestFlow`.
- Detecção automática de novos ZIPs na pasta Downloads.
- Atualização Studio + Mobile em uma única operação, com backup/rollback e preservação de `data`.
- Dependências Mobile passam a ser atualizadas automaticamente quando `package.json` muda.
- `ATUALIZAR_QUESTFLOW_SEGURO.bat` redireciona para o Manager.

## 6.9.8 - Mobile Time Focus & Visual Refresh
- Cronômetro do app contabiliza tempo ativo somente na aba Questões.
- Formatação humana de duração (segundos/minutos/horas).
- Redesign da aba Perfil com separação entre Studio local, endpoint atual e fallback cloud.
- Ajuste visual do app com navegação inferior e cards mais profissionais.
- Melhorias de legibilidade no fluxo de responder questão e visualizar feedback.

# 6.9.7 + QuestFlow Mobile 0.4 — Study Triage

- Adiciona duas ações antes da resposta no Mobile: **Corrigir questão** e **Assunto ainda não estudado**.
- **Corrigir questão** cria/reativa uma solicitação na fila de correções do Studio, suspende a questão e não cria tentativa de desempenho.
- **Assunto ainda não estudado** cria um backlog por matéria/assunto/aula, exclui o conteúdo das próximas sessões e não conta como erro, acerto, tentativa ou tempo de resposta.
- O Progresso passa a exibir **Ainda não estudados** com ação **Já estudei — liberar para questões**.
- O Mobile mantém bloqueios locais para evitar que conteúdo marcado reapareça durante períodos offline/Cloud Bridge.
- A tela Hoje mostra a quantidade de assuntos ainda não estudados.
- A fila moderna do Studio passa a ser apresentada como **Correções solicitadas**, recebendo pedidos do Mobile e do Telegram.
- Novos eventos idempotentes: `question_correction_requested`, `topic_not_studied_reported` e `topic_study_completed`.
- Contrato `questflow.mobile.v1` e schema lógico v1 preservados; Mobile atualizado para 0.4.0.

---

## 6.9.6 HOTFIX1 — Windows Update/Migration

- Corrige falha `WinError 123` no backup pré-atualização em instalações Windows.
- Backup pré-update passa a ficar fora de `data/`, com caminho mais curto e fallback seguro.
- Adiciona `MIGRAR_DADOS_DA_VERSAO_ANTERIOR.bat` para migrar dados da 6.9.5 para uma pasta 6.9.6 nova sem alterar a instalação anterior.
- Validação SQLite antes/depois da migração e backup independente para rollback.

# 6.9.5 + QuestFlow Mobile 0.2.1 — Ciclo de aparelhos

- Unifica a linguagem da interface em **Conectar / Desconectar**; “Revogar” deixa de aparecer para o usuário.
- Mantém um `device_id` persistente no SecureStore, independente da sessão, permitindo reconectar o mesmo aparelho sem duplicá-lo.
- Adiciona estado **Desconectado** e separa contadores de conectados/desconectados.
- Adiciona **Remover da lista** para ocultar registros desconectados sem apagar histórico de estudo.
- Novo pareamento reativa um aparelho previamente desconectado/oculto quando o `device_id` é o mesmo.
- Preserva `questflow.mobile.v1` e mantém alias interno de revogação apenas para compatibilidade técnica com 6.9.4.

---

# 6.9.4 + QuestFlow Mobile 0.2 — Study Coach

- tela Hoje mobile orientada por decisão: o que acontece, por que importa e o que fazer agora;
- Progresso mobile com leitura rápida, tendência recente, amostra, assuntos fracos e interpretação por matéria;
- histórico recente unificado de Aplicativo, Telegram e Studio;
- contagem de respostas por canal e Quality Gate de tempo explicado no app;
- endpoint autenticado para pausar/retomar somente novas questões do Telegram;
- listener Telegram continua ativo para respostas/comandos enquanto os envios ficam pausados;
- contrato `questflow.mobile.v1` e schema lógico v1 preservados de forma aditiva;
- Mobile atualizado para 0.2.0; rede dinâmica, SecureStore, SQLite/outbox e sync idempotente mantidos.

# 6.9.2 + QuestFlow Mobile 0.1.1 — Rede dinâmica

- Corrige seleção de IPv4 quando o computador muda de Wi-Fi/LAN.
- Prioriza o endereço da rota padrão do sistema em vez de ordenar adaptadores alfabeticamente.
- Recalcula endereços LAN no momento do status e de cada novo pareamento.
- QR de pareamento pode transportar múltiplos endereços locais seguros como fallback.
- Mobile redescobre automaticamente o Studio na sub-rede atual quando o IP salvo deixa de responder.
- Endereço redescoberto é persistido sem perder sessão, outbox ou histórico local.
- Dependências do Expo SDK 57 corrigidas e expo-dev-client incorporado ao projeto.

# 6.9.1 + QuestFlow Mobile 0.1 Alpha

- primeiro cliente móvel funcional React Native/Expo/TypeScript em `mobile/`;
- navegação Hoje / Questões / Progresso / Perfil;
- pareamento QR agora inclui endereço local da Mobile API além do token temporário, sem colocar credenciais administrativas no QR;
- endpoint público mínimo `/api/v1/mobile/health` para descoberta e validação do Studio antes do pareamento;
- SQLite local com cache de questões sem gabarito, tentativas e outbox persistente;
- resposta offline com sincronização posterior e ACK idempotente;
- evento imutável persistido com `process_status=error` pode ser reprocessado com o mesmo conteúdo; reutilização do mesmo `event_id` com conteúdo alterado continua rejeitada;
- confiança coletada antes do resultado, dificuldade opcional e lacuna “preciso revisar”;
- feedback contra a `question_revision` efetivamente apresentada;
- `client_active_timer_v1`: background e longos períodos sem interação não contaminam o tempo ativo;
- guardrail de 60 s sem interação no cliente + Quality Gate adicional no Studio;
- push opt-in por aparelho, revogação de sessão e limpeza dos dados locais;
- scripts Windows para instalar/iniciar o Alpha;
- contrato OpenAPI/documentação atualizados para 6.9.1.

# 6.9.0 — Mobile Integration Foundation

- API versionada `/api/v1/mobile/*` separada do schema interno.
- Identidade `account/tenant/learner` e control plane database-per-tenant.
- Pareamento temporário de uso único com QR gerado localmente; tokens do banco não são colocados no QR.
- Registro e revogação de dispositivos e push token.
- `learning_events` imutáveis e idempotentes por `event_id`.
- `device_id`, `session_id`, `attempt_id`, `exam_project_id` e origem `mobile_ios/mobile_android`.
- `question_revision` + snapshots para avaliar a tentativa contra a revisão realmente apresentada.
- Sync push/pull por cursor, adequado a outbox offline do futuro cliente.
- Mobile Projections: bootstrap, hoje, prioridades, progresso e lotes de questões.
- Quality Gate de temporização: tempo ativo separado de wall-clock e inatividade; amostras abandonadas/contaminadas não entram nas médias nem nos sinais de velocidade do FSRS/KT/IRT/adaptive engine.
- Dados legados de tempo são preservados para auditoria como `legacy_unverified`.
- Painel de Fundação Mobile em Configurações, com status, pareamento e dispositivos.
- 6 testes específicos novos e regressão selecionada 41/41 aprovada durante a implementação.

# 6.8.4 — Retrieval Quality Gates + promoção segura de release

- Quality Gates objetivos para score, recall, grounding e cobertura do índice.
- Release em quarentena quando regressões excedem thresholds.
- Botão `Quality Gates` sempre visível no topo de Revisar Banco.
- Promoção humana explícita e baseline aprovada separada da baseline de calibração.
- Override humano auditado com justificativa mínima e sem autoaprovação.
- Rollback de baseline/perfil de retrieval aprovado.
- Exportação de relatório de aprovação/reprovação em JSON/CSV.
- Knowledge Engine 3.4; seis motores preservados; nenhuma nova migração SQLite.

- **6.8.3 Hotfix 1:** auditoria dos controles do Roadmap; ferramentas RAG 6.8.0–6.8.3 passam a ter atalhos visíveis no topo de Revisar Banco; ações condicionais importantes deixam de desaparecer e passam a indicar indisponibilidade.

## 6.8.3 — Retrieval Observability + Dataset de Regressão Expandido

- histórico temporal de score/recall/grounding/cobertura por release e perfil;
- fingerprints locais para drift de chunks e fontes sem expor conteúdo/caminhos;
- comparação entre releases e acompanhamento por matéria;
- sugestões de expansão das Questões Ouro, sempre dependentes de aprovação humana;
- exportação de relatórios JSON e CSV;
- Knowledge Engine 3.3; exatamente seis motores preservados.

## 6.8.2 — Reranking calibrado + regressão contínua de retrieval

- reranker híbrido com features e pesos explícitos;
- grade determinística de perfis candidatos, sem LLM escolhendo pesos;
- A/B offline sobre Questões Ouro com objetivo publicado;
- promoção somente por confirmação humana;
- histórico versionado e rollback do perfil;
- baseline de retrieval por release e por matéria;
- alertas de queda de score, recall e grounding com thresholds versionados;
- Knowledge Engine 3.2; seis motores preservados; sem migração SQLite.

- 6.8.1: Benchmark Multimodal & Grounding Quality com Questões Ouro, comparação text/visual/hybrid, precisão/recall, suporte, cobertura visual e ganho híbrido.

- 6.8.0 Hotfix 6: espera adaptativa do Google Modo IA, recaptura após estabilização, captura do menor bloco Gabarito+Explicação e editor ultra-compacto com cabeçalho recolhível.

- 6.8.0 Hotfix 5: editor da questão compactado para ampliar a área útil de visualização da explicação e reduzir a altura do cabeçalho, da barra de pesquisa assistida e dos botões de revisão.

# 6.8.0 Hotfix 4 — Retorno do Google Modo IA para o editor

- o contexto da consulta pelo enunciado passa a validar respostas do Modo IA que não repetem código/banca/ano;
- o coletor prioriza o menor bloco visível contendo `Gabarito` + `Explicação/Justificativa/Resolução`;
- confiança baixa deixa de eliminar comentário já vinculado à questão e passa a ser alerta de revisão;
- reproduzido e corrigido o cenário Q105746 em que o Google exibia a explicação, mas o QuestFlow a recusava.

# Changelog

## 6.8.0 Hotfix 3 — Extração tolerante + interface organizada

- corrigido falso negativo quando o Google encontra a justificativa sem repetir Qxxxx, banca ou ano;
- consulta por código exato passa a ancorar a correspondência do Modo IA;
- justificativa inline em `Gabarito: X. Isso porque...` passa a ser preservada;
- confiança automática deixa de ser corte binário: baixa confiança gera aviso e revisão humana, não descarte da resposta;
- limpeza de metadados, enunciado, alternativas, menus e conteúdo relacionado permanece ativa;
- bloco integral da página continua proibido como comentário;
- área de pesquisa e ações do editor reorganizadas;
- botões de Curadoria simplificados para `Salvar rascunho` e `Concluir revisão`;
- 419/419 testes aprovados em quatro partições (97 + 106 + 117 + 99).

## 6.8.0 Hotfix 2 — Pesquisa IA conclui e preenche a explicação

- corrigida incompatibilidade entre a diretiva curta da 6.8.0 e o detector de estabilidade do Google: a resposta não precisa mais repetir o código Qxxxx para ser aceita;
- respostas concisas com gabarito + justificativa passam a encerrar a espera assim que estabilizam;
- o capturador semântico aceita blocos curtos de resposta, sem voltar a copiar menus/metadados;
- uma captura útil não dispara nova navegação apenas porque a flag visual do Google ainda veio como instável;
- limites de espera/CAPTCHA foram reduzidos e a interface recebe progresso por etapa;
- quando o Modo IA não produz justificativa verificável, o QuestFlow usa a Pesquisa Google para localizar uma fonte pública correspondente e extrai somente a justificativa validada;
- o gabarito local continua soberano e nenhuma explicação é salva automaticamente;
- 415/415 testes de regressão aprovados em quatro partições (111 + 101 + 106 + 97).

## 6.7.3 — Production Hardening / Build Reprodutível

- dependências principais fixadas exatamente em `requirements.lock`;
- SHA-256 do lock validado pelo instalador;
- SBOM CycloneDX, auditoria de vulnerabilidades e matriz 3.11–3.14;
- backup consistente com verificação e teste de restauração;
- atualizador seguro com staging, quick_check, smoke test e rollback;
- CI local reprodutível via `release_tools.py`;
- seis motores e schemas preservados.

## 6.7.2 — Pesquisa Google para comentários
- botão dedicado “Pesquisar resposta no Google com IA” diretamente em Explicação após a resposta;
- usa o código da questão como primeira chave de pesquisa e o enunciado como fallback;
- usa também alterações ainda não salvas do editor como contexto da pesquisa;
- preenche a explicação e define automaticamente a origem como “IA assistida + revisão humana”;
- não sobrescreve o gabarito local; divergências do Google viram alerta;
- resultado permanece como rascunho até salvar/concluir a revisão humana;
- pesquisa é auditada no Evaluation & Governance Engine com fontes e avaliação independente;
- modo Privado bloqueia a pesquisa externa de forma explícita;
- sem nova migração; seis motores preservados.

## 6.7.1 — Benchmark pedagógico e coleta de evidências
- “Coletar evidência” virou fluxo acionável e explicativo, não apenas um rótulo;
- mini-simulado diagnóstico focado no conceito e limitado a questões de alto valor informativo;
- encerramento antecipado quando o Learner Model atinge evidência suficiente;
- respostas diagnósticas alimentam FSRS + KT + IRT com origem própria;
- benchmark do scaffolding cruza nível de ajuda/representação com revisões posteriores;
- janelas de retenção imediato/1d/3d/7d/30d;
- tendências somente com amostra mínima e ressalva observacional;
- sem nova migração; seis motores preservados.

## 6.6.8 — Runtime Watchdog & Self-Healing
- supervisor central dos serviços internos, sem criação de sétimo motor;
- estados de saúde, heartbeat por serviço e autorrecuperação com cooldown/limite de reinícios;
- event loop assíncrono único para I/O e concorrência limitada por semáforo;
- rate limiting local para IA, Turso e monitor de atualizações;
- journal rotativo do Watchdog, histórico de tarefas limitado e rotação do log de startup;
- painel de saúde, recuperação manual e histórico recente em Configurações;
- relatório de compatibilidade de Python, SQLite, schemas, sistema e dependências;
- Cloud Sync offline-first preservado;
- sem nova migração do banco.

## 6.6.7 — Enunciado Contextual
- validação contextual do enunciado e remoção do limite fixo de 40 caracteres.

## 6.9.3 — Study Insights & Channel Control
- Quality Gates: amostra insuficiente agora aparece como **AGUARDANDO AMOSTRA**, sem marcar Score/Recall/Grounding como "OK" quando não foram avaliados.
- Visão Geral: novo bloco **Entenda em 30 segundos** com leitura atual, próxima ação, origem das respostas e interpretação do tempo ativo.
- Histórico recente unificado: respostas do Mobile e Telegram com certo/errado, canal e tempo ativo confiável.
- Painel Visual: nova **Decisão de estudo** explicando o que priorizar, por que e o que fazer; métricas técnicas FSRS/KT/IRT ficam recolhidas em análise avançada.
- Telegram: botão persistente para **Pausar envio de questões** sem desligar o listener ou apagar histórico. A pausa bloqueia novos ciclos, reenvios e relearning; respostas e comandos continuam sendo registrados.
- Learning analytics: resumo de atividade por canal e Quality Gate de tempo ativo incorporado ao dashboard.
# 6.21.0 — 2026-08-21

- Refatoração responsiva das 15 rotas do Studio, eliminando grids genéricos e áreas mortas estruturais.
- Dashboards educacionais com KPIs acionáveis, tendências, barras comparáveis, heatmaps e detalhes progressivos.
- Estado/eventos/DOM centralizados, acessibilidade, preservação de foco/scroll e abort de requisições de rotas antigas.
- Mobile 0.14.0 com cinco jornadas redesenhadas, gráficos SVG acessíveis e analytics v2 baseado em dados reais.
- Endpoint e bridge `AnalyticsSnapshotV2`; compatibilidade mantida com `/api/v1/mobile/progress`.
- Pacote seguro com Mobile incluído, preservação do banco e rollback.
