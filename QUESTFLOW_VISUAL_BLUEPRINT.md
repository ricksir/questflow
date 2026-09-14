# QuestFlow — direção visual e de experiência

## Objetivo

Evoluir QuestFlow Studio e QuestFlow Mobile preservando integralmente contratos, dados, histórico, FSRS, KT, IRT, filas offline e sincronização, mas adotando uma linguagem visual e uma experiência de estudo mais coerentes.

## Referências escolhidas

### Schoolab — referência visual principal

Aproveitar:

- composição limpa e educacional;
- contraste entre navegação escura e superfícies claras;
- base quente/off-white;
- amarelo/âmbar como ação principal;
- verde/teal para domínio/sucesso;
- azul como informação;
- coral/vermelho para risco;
- cards com muito respiro e hierarquia forte;
- barras, anéis e estados de nível com leitura imediata.

Não copiar telas nem assets. O QuestFlow mantém identidade própria.

### Aprova.ai — referência de jornada

Aproveitar a lógica de transformar diagnóstico em próximo passo:

1. abrir o produto e saber o que estudar agora;
2. mostrar plano do dia antes de análises profundas;
3. priorizar matérias/assuntos por evidência;
4. integrar questões, revisão espaçada e recomendação;
5. usar IA de forma contextual, ligada ao estudo atual;
6. permitir replanejamento sem destruir histórico.

Princípio: **dados devem terminar em uma ação clara**.

### Checkmate — referência analítica

Aproveitar variedade e composição de visualizações:

- linha/área para evolução;
- barras para comparação por matéria/assunto/banca;
- donut/anéis para domínio e cobertura;
- heatmap para consistência;
- matrizes/quadrantes para confiança x desempenho;
- cartões KPI para resumo;
- séries temporais para retenção e atividade.

Princípio: **gráfico só entra quando responde a uma pergunta de estudo**.

### Fynix — referência de inteligência contextual e densidade

Aproveitar:

- assistente contextual integrado ao dashboard, não isolado em uma tela de chat;
- síntese curta de sinais complexos com uma ação recomendada;
- cards compactos e bem hierarquizados;
- dashboards densos sem parecerem pesados;
- atividade recente como registro operacional de fácil leitura;
- indicadores que respondem perguntas específicas.

No QuestFlow, o bloco **Quest AI · insight contextual** deve ser montado apenas com evidências reais já disponíveis no Learning Engine. Ele não cria um “score” artificial e não substitui FSRS, KT, IRT ou o Recomendador.

Princípio: **inteligência contextual deve explicar o que os dados significam e oferecer um próximo passo, sem inventar métricas**.

### Fórmula do produto

**QuestFlow = Schoolab (identidade visual) + Aprova.ai (jornada de estudo) + Checkmate (capacidade analítica) + Fynix (inteligência contextual e densidade controlada).**

## Design tokens

A paleta abaixo é uma adaptação operacional da linguagem visual observada no Schoolab. Os HEX não são apresentados pelo Behance em texto estruturado, portanto são aproximações deliberadas para o QuestFlow, não uma alegação de cópia exata.

| Papel | Token | Valor |
|---|---|---|
| Navegação escura | `--qf-ink-900` | `#1D223B` |
| Fundo principal | `--qf-warm-50` | `#FBFAF6` |
| Fundo secundário | `--qf-warm-100` | `#F6F2E9` |
| Ação principal | `--qf-gold-500` | `#F3B54A` |
| Ação forte | `--qf-gold-600` | `#DC972E` |
| Sucesso/domínio | `--qf-teal-500` | `#21B89A` |
| Informação | `--qf-sky-500` | `#55A9D6` |
| Risco/erro | `--qf-coral-500` | `#EF7868` |
| Atenção | `--qf-yellow-400` | `#F4CF4F` |
| Texto | `--qf-text` | `#25283A` |
| Texto secundário | `--qf-muted` | `#7C8192` |
| Bordas | `--qf-border` | `#E8E2D8` |

## Arquitetura desejada

### Studio

O Studio continua sendo o cérebro do QuestFlow.

Ordem de atenção da tela inicial:

1. **Próxima melhor ação**
2. plano de estudo do dia
3. **Quest AI · insight contextual**
4. revisões vencidas/próximas
5. consistência/meta semanal
6. prioridades por matéria
7. analytics aprofundado

O painel analítico deve permitir aprofundamento por matéria, assunto, banca e período sem inventar séries temporais.

### Mobile

O Mobile continua Study Only.

A tela Hoje deve priorizar:

1. atividade recomendada;
2. duração estimada;
3. revisões e questões da sessão;
4. progresso do dia;
5. sincronização de forma discreta.

Analytics detalhado permanece no Studio; o Mobile mostra apenas o necessário para decidir e agir.

## Regras de implementação

- preservar os dados reais e seus contratos;
- não criar métricas falsas para preencher cards;
- manter acessibilidade de teclado/foco no Studio;
- manter alvos de toque adequados no Mobile;
- preservar dark mode quando viável;
- não alterar motor adaptativo para fins puramente visuais;
- mudanças estruturais entram em etapas e com regressão coberta;
- nenhuma release é criada só por mudar a aparência, salvo pedido explícito.

## Etapas

1. Fundação visual compartilhada.
2. Home/Visão geral orientada à próxima ação.
3. Analytics com linguagem Checkmate.
4. Insight contextual e densidade de dashboard com linguagem Fynix.
5. Fluxos de questões e revisão.
6. Mobile Today/Progress com a mesma identidade.
7. Polimento responsivo, acessibilidade e dark mode.
