# O que mudou na versão 5.0

## Alterado

### Interface principal

**Antes:** interface nativa Tkinter, com caixas de texto de altura fixa e responsividade limitada.

**Agora:** interface HTML/CSS/JavaScript local incorporada por pywebview, com layout responsivo, temas, acessibilidade e virtualização.

### Editor de questões

**Antes:** enunciado, alternativas e explicação eram caixas simples; as alternativas usavam uma linha por opção no formato `A|texto`.

**Agora:**

- enunciado e explicação têm editor rico em layout, autoaltura e expansão;
- alternativas são campos independentes;
- há validação visual, cópia, normalização e prévia;
- os controles se reorganizam por Container Queries.

### Lista de questões

**Antes:** tabela nativa carregava todos os itens visíveis no widget.

**Agora:** lista virtualizada renderiza apenas as linhas necessárias ao viewport, mantendo busca, filtros e seleção.

### Temas e escala

**Antes:** aparência dependia principalmente do tema Tkinter e ajustes parciais de fonte.

**Agora:** tokens centralizados, claro/escuro automático e manual, escala 80–200%, densidade e foco consistente.

### Integração

**Antes:** a UI chamava os serviços Python pela camada Tkinter.

**Agora:** `web_api.py` valida a fronteira JavaScript/Python e reutiliza os mesmos serviços e banco.

## Mantido intacto

- formato e migrações do banco SQLite;
- extração de PDF e OCR;
- classificação pela planilha;
- regras de aprovação/anulação;
- motor adaptativo e ciclo de estudo;
- Telegram e correções;
- mapa de aulas;
- importação/exportação;
- interface clássica como fallback.

## Por que a mudança foi necessária

Os requisitos de CSS Grid, Flexbox, Container Queries, `clamp()`, `prefers-color-scheme` e estados web completos não são recursos de Tkinter. A arquitetura híbrida atende esses requisitos sem reescrever as regras do QuestFlow.
