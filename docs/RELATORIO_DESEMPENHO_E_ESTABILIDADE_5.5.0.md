# QuestFlow Studio 5.5.0 — Revisão de desempenho e estabilidade

Data da revisão: 10/08/2026

## Objetivo

Revisar o pacote completo do QuestFlow Studio com foco em travamentos, lentidão de abertura, consumo desnecessário de memória, concorrência entre tarefas, sincronização Turso, atualização da interface, Telegram, servidor HTTP local e crescimento do SQLite ao longo do uso.

## Correções aplicadas

### 1. Fluxo Telegram que podia parar de atualizar após muitos eventos
O histórico em memória mantém somente os 200 eventos mais recentes. O cursor anterior dependia do tamanho dessa lista; quando ela chegava a 200 itens, novos eventos podiam substituir os antigos sem avançar corretamente a leitura da interface. O cursor agora é absoluto e continua avançando mesmo quando o buffer gira.

### 2. Acúmulo de tarefas em memória
O registro de tarefas de background podia crescer durante sessões longas. Foi criado limite de histórico e limpeza automática de tarefas encerradas. Carregamentos equivalentes de bootstrap/dashboard também passam a ser coalescidos, evitando duplicação de trabalho.

### 3. Verificação de saúde do banco muito pesada e sobreposta
A tela VISÃO GERAL fazia verificações profundas repetidas do SQLite e várias chamadas de rede ao Turso. Agora:
- a integridade profunda local é reutilizada por 5 minutos quando continua válida;
- uma nova verificação de saúde não começa enquanto a anterior ainda está executando;
- a atualização automática usa loop encadeado em vez de `setInterval`, evitando sobreposição;
- falhas silenciosas temporárias de rede não substituem imediatamente um estado saudável já exibido.

### 4. Turso: menos viagens de rede no painel de saúde
Contagem lógica de questões, geração e maior sequência remota passam a ser consultadas em um único lote SQL-over-HTTP. Também foi adicionado índice por `table_name`, `row_key` e `seq` no log remoto, reduzindo o custo da contagem lógica à medida que o histórico cresce.

### 5. Fechamento que podia parecer congelado durante sincronização
Se já existe uma sincronização Turso em andamento, o fechamento não inicia outra sincronização bloqueante atrás do mesmo lock. O encerramento informa que o envio ficou deferido; a outbox SQLite durável preserva as alterações para a próxima sincronização.

### 6. Cache técnico local do Cloud Sync sem limite
`qf_sync_inbox` funcionava como cache de deduplicação e podia crescer indefinidamente. Foi adicionado índice por sequência e retenção limitada da cauda recente, evitando crescimento contínuo do arquivo local por dados que já não são necessários à operação normal.

### 7. Dashboard abre com conteúdo útil mais cedo
Quando existe snapshot anterior do dashboard, ele é exibido imediatamente enquanto a atualização completa roda em background. Isso reduz a sensação de tela vazia ou congelada.

### 8. Heartbeat da interface sem sobreposição
O heartbeat HTTP deixou de usar um intervalo fixo que podia iniciar nova requisição antes da anterior terminar. Agora a próxima execução só é agendada após a conclusão da atual e adapta a frequência quando a janela está oculta.

### 9. Lista virtual com menos recalculo de layout
A medição da altura das linhas deixou de criar/remover um elemento temporário do DOM a cada ResizeObserver. O valor em `rem` é resolvido diretamente a partir do tamanho da fonte raiz, reduzindo layout thrashing.

### 10. Porta local estável com fallback automático
O servidor preferirá a porta local `53155`. Isso mantém a mesma origem no Chrome e faz tema, zoom e preferências de colunas salvos em `localStorage` persistirem melhor entre aberturas. Se a porta estiver ocupada, o servidor escolhe automaticamente outra porta e continua abrindo normalmente.

### 11. Arquivos estáticos sem risco de versão antiga na interface
JS/CSS/HTML críticos são entregues com política que evita reutilização de uma versão antiga incompatível com o núcleo Python durante atualização local.

### 12. Parada mais responsiva do motor de fluxo
Esperas internas do agendador/listener do Telegram passam a responder ao evento de parada, em vez de aguardar sleeps completos de 1–5 segundos quando isso não é necessário.

### 13. Metadados de versão alinhados
`pyproject.toml` e o cabeçalho do servidor local foram alinhados à versão 5.5.0.

### 14. Pacote final limpo
Caches Python (`__pycache__`/`.pyc`) e bancos gerados apenas pelo diagnóstico não fazem parte do ZIP otimizado.

## Validação automatizada

- `python -m compileall`: aprovado.
- `node --check web/app.js`: aprovado.
- suíte completa: **199 testes executados, 199 aprovados**.
- foram adicionados 6 testes de regressão específicos para estabilidade/performance:
  - cursor de eventos após rotação do buffer de 200 itens;
  - coalescência de tarefas concorrentes;
  - limite do histórico de tarefas;
  - consulta de saúde Turso em lote;
  - fechamento sem bloqueio atrás de sincronização ativa;
  - fallback de porta e política de cache do servidor local.
- diagnóstico interno do QuestFlow: **concluído sem falhas locais**.

## Teste sintético com 20.000 questões

Medições no ambiente de validação desta revisão; servem para comparação técnica e não como garantia de tempo no Windows do usuário.

| Operação | Média observada |
|---|---:|
| Paginação (100 itens, offset 10.000) | 1,32 ms |
| Busca textual comum | 9,40 ms |
| Busca por código específico | 17,67 ms |
| Filtro por status | 1,60 ms |
| Saúde SQLite — primeira verificação profunda | 20,32 ms |
| Saúde SQLite — verificação reaproveitando cache | 1,55 ms |

Também foi medido o caminho de abertura local com a base do pacote:
- inicialização leve da API: ~0,20 ms;
- bootstrap da casca da interface: ~72,69 ms;
- início do servidor HTTP local: ~1,12 ms;
- entrega inicial do `index.html`: ~9,63 ms.

## Pontos que dependem do computador real

O ambiente de validação não possui Google Chrome instalado nem credenciais reais do Telegram/Turso. O diagnóstico confirmou o modo local, o protocolo HTTP/JSON, SQLite, taxonomia, pipeline, agendamento e módulos internos, mas a validação final de rede deve ser feita no próprio computador por meio de:
- abertura normal no Google Chrome;
- botão **Testar bot** para Telegram;
- painel/configuração **Cloud Sync** para o banco Turso real;
- eventual proxy corporativo da rede utilizada.

## Resultado

A revisão concentrou-se em eliminar trabalho duplicado, impedir crescimento desnecessário de estruturas de memória/banco, evitar verificações de saúde concorrentes e tornar inicialização/fechamento mais previsíveis. Não foi necessária troca de tecnologia de banco nem migração arriscada da base de questões.
