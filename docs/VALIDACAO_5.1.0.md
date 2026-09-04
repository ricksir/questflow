# Validação técnica — QuestFlow Studio 5.1.0

## Escopo

Esta validação cobre as correções de inicialização, ponte Python–JavaScript, banco SQLite e responsividade solicitadas para a versão 5.1.0.

## Verificações executadas

- suíte automatizada completa: **111 testes aprovados**;
- compilação dos módulos Python com `compileall`;
- validação sintática de `web/app.js` com Node.js;
- diagnóstico integrado do projeto em cópia isolada;
- inspeção visual automatizada das telas **Revisar banco**, **Fluxo Telegram** e **Mapa de aulas**, em resolução de 1564 × 990;
- confirmação de que o bootstrap visual retorna antes de inicializar o núcleo pesado;
- confirmação de paginação SQL e migrações idempotentes dos novos índices.

## Resultados observados

### Inicialização

A construção da API e o retorno do shell visual não dependem mais da abertura do banco de estudos, do motor adaptativo ou do fluxo Telegram. Esses componentes são inicializados uma única vez em segundo plano.

Em uma medição local de desenvolvimento, com a base fornecida no ZIP, o shell foi retornado de forma imediata e a preparação completa do núcleo ficou abaixo de 0,2 segundo. Esse número é apenas uma amostra do ambiente de validação; o tempo no Windows também depende do disco, antivírus, versão do Python e tamanho real da base.

### Ponte nativa

O JavaScript só considera a ponte pronta quando o método solicitado realmente existe em `window.pywebview.api`. Isso evita a chamada prematura que produzia o aviso **“A função bootstrap_shell não está disponível”**.

### Banco e consultas

- contadores foram agrupados em consultas agregadas;
- novos índices atendem lista, cobertura, tentativas e entregas;
- o primeiro lote da revisão tem limite seguro;
- buscas antigas são descartadas quando uma consulta mais recente termina primeiro;
- o Mapa de aulas usa os mesmos nomes de campos e códigos de situação no backend e no frontend.

### Interface

A inspeção visual confirmou:

- menu lateral recolhido sem textos sobrepostos;
- lista de revisão com colunas úteis e textos longos em até duas linhas;
- editor ajustado à altura útil da janela;
- controles compactos no Fluxo Telegram;
- ausência da linha de foco horizontal que atravessava a tela;
- Mapa de aulas preenchido, com quebra de texto e indicadores de situação;
- botões, filtros e painéis sem recortes nas telas verificadas.

## Preservação de dados

O ZIP final mantém os arquivos de dados recebidos no pacote original. As novas migrações são executadas automaticamente na primeira abertura da versão 5.1.0 e são idempotentes.
