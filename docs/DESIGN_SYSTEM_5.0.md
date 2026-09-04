# Design System do QuestFlow Studio 5.0

## Princípios

1. **Clareza operacional:** cada tela apresenta uma ação principal e reduz ruído visual.
2. **Responsividade intrínseca:** componentes reagem ao próprio container.
3. **Consistência:** cor, espaçamento, tipografia, movimento e estados vêm de tokens.
4. **Acessibilidade por padrão:** foco, teclado, rótulos e contraste fazem parte do componente.
5. **Desempenho progressivo:** listas extensas são virtualizadas e conteúdos pesados são carregados sob demanda.

## Arquitetura visual

A aplicação usa três níveis:

```text
app-shell
├── sidebar responsiva
└── app-stage
    ├── topbar
    └── workspace
        └── páginas e painéis por container
```

No desktop, a navegação é lateral. Em larguras menores, a barra se recolhe e os painéis passam de múltiplas colunas para uma única coluna. O editor de revisão alterna automaticamente entre lista + editor e uma pilha vertical.

## Tokens

Os tokens são definidos em `web/styles.css` no seletor `:root`:

- `--font-*`: famílias e escala tipográfica;
- `--font-size-*`: tamanhos fluidos com `clamp()`;
- `--space-*`: escala modular de espaçamento;
- `--radius-*`: raios consistentes;
- `--surface-*`, `--text-*`, `--border-*`: cores semânticas;
- `--accent-*`, `--success-*`, `--warning-*`, `--danger-*`: estados;
- `--shadow-*`: elevação;
- `--motion-*`: tempos e curvas;
- `--sidebar-width`, `--topbar-height`: dimensões estruturais.

Nenhum componente novo deve introduzir cor ou espaçamento arbitrário quando existir um token semântico equivalente.

## Caixas de texto modernizadas

O enunciado e a explicação usam o componente `.rich-text-field`:

- `min-height` e `max-height` fluidos;
- redimensionamento vertical permitido;
- autoajuste via JavaScript;
- toolbar contextual;
- contador e validação;
- modo expandido em modal;
- foco visível;
- suporte completo a seleção e atalhos.

As alternativas usam linhas estruturadas, cada uma com chave, campo de texto e ação de remoção. Isso evita editar uma grande string delimitada por `|` e reduz erros de formatação.

## Temas

- O modo do sistema é respeitado por `prefers-color-scheme`.
- O usuário pode alternar manualmente entre claro e escuro.
- A preferência é salva localmente.
- `color-scheme` permite que controles nativos acompanhem o tema.

## Estados

Cada componente interativo possui, conforme aplicável:

- padrão;
- hover;
- focus-visible;
- active;
- disabled;
- loading;
- skeleton;
- erro;
- vazio;
- selecionado.

Animações usam apenas `transform` e `opacity`. Em `prefers-reduced-motion: reduce`, transições e animações são reduzidas.

## Acessibilidade

- landmarks semânticos (`aside`, `nav`, `main`, `section`);
- skip link;
- `aria-label`, `aria-live`, `aria-modal` e `aria-current`;
- foco preso em modais e devolvido ao elemento de origem;
- navegação por teclado;
- área mínima de clique compatível com toque;
- cores semânticas com contraste direcionado a WCAG AA;
- conteúdo permanece utilizável a 200% de zoom.

## Responsividade testada por projeto

- mobile portrait: navegação recolhida, uma coluna, controles empilhados;
- mobile landscape: ações compactadas e editor com maior largura útil;
- tablet: painéis adaptativos em uma ou duas colunas;
- desktop: lista e editor simultâneos;
- ultrawide: largura de leitura limitada e uso eficiente de colunas;
- zoom 200%: componentes quebram linha e não dependem de largura fixa.
