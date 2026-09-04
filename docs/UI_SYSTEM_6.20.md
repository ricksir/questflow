# QuestFlow UI 6.20 — sistema transversal de layout e estado

## Resultado

A atualização deixa de tratar somente a Visão geral. Todas as 15 áreas do Studio e as cinco superfícies principais do Mobile passam a compartilhar contratos de layout, estado e acessibilidade.

## Organização das áreas

| Grupo | Áreas |
|---|---|
| Planejamento | Visão geral, Painel visual, Projeto e edital |
| Banco de questões | Importar, Curadoria inteligente, Revisar banco, Corrigir banco |
| Aprendizagem e IA | Tutor IA, Recomendador e simulados, Geração e legislação |
| Rotina e sincronização | Correções, Estudos e questões, Fluxo Telegram, QuestFlow Mobile |
| Sistema | Configurações |

## Contrato de layout do Studio

- Cada página observa a própria área útil e recebe `data-layout="wide|standard|compact"`.
- A grade raiz usa `minmax(0, 1fr)` para impedir que conteúdo interno aumente a largura da página.
- Tutor: fila e workspace lado a lado em `wide`; duas filas na primeira linha e workspace completo em `standard`; uma coluna em `compact`.
- Recomendador e Geração: decisão e configuração permanecem lado a lado quando há espaço; painéis de detalhe ocupam linhas completas.
- Configurações, Fluxo, Curadoria e Mobile usam preenchimento denso, sem reservar colunas para cartões ausentes.

## Contrato de estado e DOM

- Abas inativas recebem `aria-hidden="true"` e `inert`.
- A aba ativa anuncia `loading`, `ready`, `degraded` ou `error`.
- Uma barra fina sinaliza carregamento sem bloquear a navegação.
- Serviços independentes usam `Promise.allSettled`; falha parcial produz estado degradado, não tela inteira quebrada.
- A rolagem é preservada por aba.
- Mudanças em conteúdo dinâmico atualizam `aria-busy`, skeletons e estados vazios.
- Eventos `questflow:route-will-change`, `questflow:route-ready` e `questflow:layoutchange` permitem instrumentação sem acoplamento.

## Contrato do Mobile

- `ScreenHeader` padroniza título, contexto e estado operacional.
- `StatePanel` representa carregamento, vazio, erro, offline, sucesso e informação.
- Hoje, Progresso, Questões, Perfil e Pareamento usam os mesmos componentes.
- Laranja representa ação; ciano representa evidência; verde/amarelo/vermelho continuam reservados a estados semânticos.

## Critérios de aceitação

- nenhuma aba produz overflow horizontal no viewport auditado;
- nenhum workspace fica escondido abaixo de uma coluna estreita por causa da largura total da janela;
- falha parcial não apaga conteúdo já carregado;
- elementos de páginas inativas não recebem foco;
- estados vazios não são confundidos com falha ou carregamento infinito.
