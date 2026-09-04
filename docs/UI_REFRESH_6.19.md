# QuestFlow UI 6.19 — cockpit adaptativo

## Princípio de produto

A interface foi reorganizada para responder, nesta ordem:

1. qual é a melhor próxima ação;
2. quais evidências justificam a recomendação;
3. como o desempenho está mudando;
4. onde investigar os detalhes.

Isso reduz a carga cognitiva sem esconder FSRS, prática intercalada, domínio, lacunas declaradas, incerteza ou qualidade dos dados.

## Studio

- Novo painel **Pulso de aprendizagem** no dashboard.
- Comando adaptativo, retenção, tendência e focos prioritários em uma mesma leitura.
- Cartões métricos com iconografia, sinal visual e cores semânticas.
- Layout responsivo para desktop compacto e tablet.

## Mobile 0.13.1

- Paleta escura unificada com ação primária laranja e evidência ciano.
- `StatRing` acessível para síntese de acurácia.
- `MicroBars` reutilizável para comparação rápida entre matérias.
- Telas Hoje e Progresso orientadas à decisão, com detalhe sob demanda.
- Contrato offline, fila de eventos e regras pedagógicas preservados.

## Diretrizes de gráficos

- Mostrar sempre rótulo, janela temporal e unidade.
- Usar cor para significado, não como única forma de distinção.
- Priorizar comparação e tendência; evitar gráficos decorativos.
- Exibir incerteza ou falta de amostra como estado explícito.
- Manter a decisão acionável próxima da evidência que a sustenta.

## Tokens principais

| Papel | Valor |
|---|---|
| Fundo | `#080D16` |
| Superfície | `#121B29` |
| Superfície elevada | `#182536` |
| Ação primária | `#FF8A2A` |
| Tendência/evidência | `#25C7D9` |
| Sucesso | `#42D98A` |
| Alerta | `#F8BE54` |
| Erro | `#FF6B7D` |
| Texto | `#F8FAFC` |
| Texto secundário | `#9CAFC4` |

No Figma, **Inter** é usada como substituta operacional de **Segoe UI Variable**, indisponível no ambiente conectado. O código continua usando a pilha tipográfica nativa do produto.
