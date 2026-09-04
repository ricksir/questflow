# Auditoria de engenharia — QuestFlow Studio 4.2

## Objetivo

Executar a etapa de redução da dívida técnica identificada na versão 4.1 sem reescrever o programa inteiro nem arriscar a base existente.

## Resultado executivo

A principal dívida estrutural foi tratada: `app.py` deixou de ser um arquivo monolítico com mais de 5.500 linhas e passou a funcionar como **composition root**, com 166 linhas. A interface e os controladores foram distribuídos por responsabilidade.

### Antes

```text
app.py
 ├── tema e shell
 ├── todas as páginas
 ├── importação
 ├── OCR e análise apurada
 ├── pesquisa web
 ├── edição
 ├── Telegram
 ├── exportação
 └── configurações
```

### Depois

```text
app.py                         composição e ciclo de vida
app_shared.py                  configuração, caminhos e tema
ui/shell_mixin.py              shell, navegação, escala e tabelas
ui/dashboard_mixin.py          Mission Control
ui/import_mixin.py             importação e fila de eventos
ui/review_layout_mixin.py      layout da revisão
ui/review_enrichment_mixin.py  enriquecimento web
ui/deep_analysis_mixin.py      releitura e análise apurada
ui/question_editor_mixin.py    edição, imagem e prévias
ui/flow_mixin.py               ciclo e Telegram
ui/corrections_coverage_mixin.py correções e mapa de aulas
ui/settings_export_mixin.py    configuração, backup e exportação
```

## Métricas estruturais

| Componente | 4.1 | 4.2 | Resultado |
|---|---:|---:|---|
| `app.py` | ~5.513 linhas | 166 linhas | composição isolada |
| maior módulo de UI | ~5.513 linhas | 870 linhas | nenhum módulo de UI acima de 1.000 linhas |
| acesso direto ao banco nas views | disseminado | 0 ocorrências | leitura/escrita por serviços |
| migrações registradas | alterações dispersas | tabela `schema_migrations` | histórico auditável |
| calibração do modelo | não medida | Brier, log loss e ECE | risco de excesso de confiança mensurável |

## Alterações implementadas

### 1. Interface modular

As abas foram extraídas para módulos independentes. O `QuestFlowApp` apenas instancia dependências, compõe os mixins, controla o fechamento e inicia os serviços.

Foram adicionados testes que falham se:

- `app.py` voltar a ultrapassar 250 linhas;
- uma view acessar `self.database` diretamente;
- algum módulo de interface ultrapassar 1.000 linhas;
- os módulos obrigatórios forem removidos.

### 2. Separação entre consultas e comandos

Foram criados:

- `QuestionQueryService`: consultas, estatísticas, listas e histórico;
- `QuestionCommandService`: atualização, importação, exclusão, arquivamento e backup.

As views não conhecem mais os métodos internos do SQLite. Isso permite incluir auditoria, cache ou outra persistência sem alterar todas as telas.

### 3. Migrações SQLite versionadas

O arquivo `core/schema_migrations.py` introduz:

- registro por componente e versão;
- checksum da migração;
- aplicação idempotente;
- histórico consultável;
- detecção de versão já aplicada com definição divergente.

Componentes registrados nesta versão:

```text
question_bank: 1, 2
study:         1, 2, 3, 4
```

O snapshot completo do esquema está em `docs/SCHEMA_4.2.sql`.

### 4. Calibração do modelo adaptativo

Cada tentativa passa a guardar:

- probabilidade prevista antes da resposta;
- versão do modelo;
- tempo de resposta.

O painel calcula:

- **Brier score**;
- **log loss**;
- **Expected Calibration Error (ECE)**;
- faixas de probabilidade versus frequência observada.

Essas métricas não alteram parâmetros automaticamente. Elas servem para decidir, com evidência, se o modelo está calibrado.

### 5. Diagnóstico compatível com arquitetura modular

O diagnóstico não procura mais eventos apenas em `app.py`. Ele verifica `app.py` e todos os módulos `ui/`, além de validar:

- composition root compacto;
- ausência de acesso direto ao banco nas views;
- migrações do banco e do motor de estudo;
- consistência da versão.

## Validação executada

- 98 testes automatizados: aprovados;
- compilação de aplicação, UI, core e testes: aprovada;
- diagnóstico integrado: sem falhas locais;
- teste gráfico em monitor virtual: aprovado;
- benchmark com 5.000 questões: aprovado;
- migração repetida e idempotência: aprovadas;
- cálculo de calibração: aprovado.

## Dívida remanescente

A atualização reduz a maior concentração de risco, mas não declara o sistema “sem dívida”. Permanecem:

| Arquivo | Linhas | Próxima ação segura |
|---|---:|---|
| `core/study.py` | ~2.204 | separar repositórios, seleção, memória e Telegram |
| `core/extractor.py` | ~1.496 | dividir estratégias por formato de documento |
| `core/enrichment.py` | ~1.378 | separar parsing, confirmação e aplicação |
| `core/flow.py` | ~1.173 | separar scheduler, listener, manutenção e envio |
| `core/google_browser.py` | ~1.062 | encapsular adaptadores de DOM e sessão |

A próxima etapa deve ser incremental e coberta por testes. Reescrever todos esses módulos de uma vez aumentaria o risco de regressão.

## Conclusão

A dívida técnica apontada na auditoria 4.1 foi efetivamente reduzida. O principal ganho não é visual: é a capacidade de modificar, testar e substituir partes do programa sem depender de um único arquivo central.
