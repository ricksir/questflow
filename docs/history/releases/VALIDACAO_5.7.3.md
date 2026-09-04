# Validação — QuestFlow Studio 5.7.3

## Objetivo
Atender ao ajuste solicitado para:
1. mover o **Painel visual** para o menu lateral esquerdo;
2. permitir clique nos cards/eventos do painel visual para abrir mais detalhes estatísticos;
3. transformar o **Resumo por matéria** em uma visão compacta/minimizada, com expansão sob clique para mostrar o detalhamento completo.

## Alterações implementadas
- Novo item no menu lateral: **Painel visual**.
- Nova página dedicada `visualanalytics` com:
  - cartões KPI clicáveis;
  - gráfico de evolução temporal;
  - gráficos de rosca;
  - comparativo por matéria;
  - resumo condensado;
  - insights rápidos.
- Interações:
  - clique nos cards/áreas do painel visual abre modal com explicações e detalhes;
  - clique nas linhas das matérias no comparativo e no resumo abre drilldown da matéria com estatísticas, aulas e assuntos frágeis.
- Em **Visão geral**, o bloco **Desempenho e prioridades por matéria** agora mostra cada matéria minimizada por padrão.
- Clique na matéria expande o conteúdo completo sem ocupar muito espaço inicialmente.

## Verificações executadas
- `node --check web/app.js` → **OK**
- `python3 -m compileall -q .` → **OK**

## Observação
A versão preserva a lógica de dados já existente; a evolução foi concentrada na apresentação e na interação do dashboard.
