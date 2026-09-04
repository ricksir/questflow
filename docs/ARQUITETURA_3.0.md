# Arquitetura QuestFlow Studio 3.0

## Camadas

### Interface — `app.py`

Coordena telas, estados visuais, filas de eventos e ações do usuário. Operações demoradas são executadas em threads e retornam resultados pela fila da interface.

### Persistência — `core/storage.py` e `core/study.py`

- SQLite com transações curtas, `busy_timeout`, WAL e fechamento explícito;
- banco rico da questão em JSON, acompanhado de colunas indexadas;
- ciclos, entregas, tentativas, desempenho e runtime do fluxo;
- migrações incrementais sem exigir recriação do banco.

### Ingestão — `core/markdown_pipeline.py` e `core/extractor.py`

- cache imutável por SHA-256;
- Markdown paginado;
- texto nativo, OCR, identificação visual e extração de figuras;
- parsers de listas/gabaritos e formato QConcursos;
- reparo conservador antes de aprovação.

### Taxonomia — `core/spreadsheet_taxonomy.py`

Mapeia a origem para matéria, aula e assunto da planilha AFRFB, mantendo confiança, método e referência.

### Telegram — `core/telegram.py` e `core/flow.py`

- validação local do quiz;
- envio de foto, contexto e enquete;
- classificação de falhas e backoff;
- scheduler, captura de respostas e comandos;
- reenvio manual, automático e em lote.

### Enriquecimento — `core/enrichment.py`

Pesquisa opcional, calcula similaridade, registra evidências e aplica somente sugestões de alta confiança em campos vazios.

### Exportação — `core/exporter.py`

Converte a estrutura rica para JSON técnico, CSV, formato nativo do QuestFlow, pacote completo e SQLite.

## Princípios aplicados

- compatibilidade retroativa;
- operações destrutivas explícitas;
- nenhuma aprovação automática baseada somente em pesquisa web;
- falha de rede não corrompe o banco;
- idempotência por código/fingerprint;
- tarefas demoradas fora da thread gráfica;
- funções puras testáveis para classificação, matemática, payloads e reparo.
