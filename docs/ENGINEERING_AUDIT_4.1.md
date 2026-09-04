# Auditoria de engenharia — QuestFlow Studio 4.1

## Resumo executivo

A revisão encontrou uma base funcional, com boa cobertura de testes e persistência local, mas com três concentrações de risco:

1. `app.py` ainda é um controlador gráfico monolítico com mais de 5.500 linhas.
2. `core/study.py`, `core/extractor.py`, `core/enrichment.py` e `core/flow.py` concentram regras de negócio extensas.
3. o motor adaptativo anterior usava uma aproximação DSR própria, sem integração opcional com uma implementação oficial do FSRS.

A versão 4.1 não tenta “embelezar” a complexidade. Ela isola novos componentes, mantém fallback e adiciona testes de idempotência, saúde e concorrência.

## Métricas observadas

| Arquivo | Linhas aproximadas | Observação |
|---|---:|---|
| `app.py` | 5.513 | maior dívida estrutural; interface e coordenação ainda juntas |
| `core/study.py` | 2.122 | persistência, seleção, memória e Telegram no mesmo repositório |
| `core/extractor.py` | 1.496 | múltiplos formatos de PDF/OCR; alto risco de regressão |
| `core/enrichment.py` | 1.378 | parsing e validação web extensos |
| `core/flow.py` | 1.173 | agendamento, filas e callbacks concentrados |
| `core/google_browser.py` | 1.062 | automação de navegador sensível a mudanças externas |

A suíte 4.1 executa 90 testes automatizados, além de diagnóstico, compilação, teste gráfico e benchmark.

## Alterações aplicadas

### 1. Agendamento de memória

- `core/fsrs_adapter.py` isola a integração com Py-FSRS 6.
- o cartão FSRS é serializado por questão.
- indisponibilidade ou incompatibilidade da dependência não interrompe o sistema: o motor DSR local continua ativo.
- respostas duplicadas não avançam novamente o estado de memória nem duplicam XP.

### 2. Política contextual de assuntos

- `core/topic_bandit.py` implementa uma política UCB interpretável.
- a prioridade combina fraqueza, risco de esquecimento, incerteza, recência e cobertura.
- a política complementa — não substitui — as restrições de aprovação, correção e rotação.

### 3. Gamificação educativa

- `core/gamification.py` calcula XP e nível de forma determinística.
- eventos de XP são idempotentes no SQLite.
- não há sorteio, caixa-surpresa, monetização, ranking público ou punição por ausência.

### 4. Concorrência e responsividade

- `core/background_runtime.py` cria um event loop isolado com concorrência limitada.
- o runtime oferece base para migrar OCR, navegador e Telegram de threads ad hoc para tarefas estruturadas.
- o encerramento cancela tarefas pendentes e fecha o loop de forma controlada.

### 5. Observabilidade

- `core/health.py` mede latência do banco, tamanho do SQLite/WAL, falhas de Telegram, fila de saída e correções pendentes.
- o Painel Mission Control mostra estado do scheduler, XP, nível e saúde operacional.

## Riscos remanescentes

- `app.py` deve ser dividido gradualmente em views, view-models e serviços; uma substituição total em uma única versão criaria risco desnecessário.
- a automação do Google Modo IA depende da interface de terceiros e sempre exigirá fallback/manual review.
- o otimizador de parâmetros FSRS não é executado automaticamente; ele exige histórico suficiente e validação antes de alterar parâmetros.
- Tkinter é adequado ao aplicativo local atual, mas uma futura interface web/desktop híbrida exigiria migração planejada, não simples troca de biblioteca.

## Próximas etapas recomendadas

1. extrair cada aba de `app.py` para `ui/pages/`;
2. separar comandos de leitura e escrita do banco;
3. migrar jobs de Telegram/OCR para o runtime assíncrono;
4. adicionar testes de carga com banco real anonimizado;
5. adicionar snapshots de esquema e migrações versionadas;
6. medir precisão/calibração do modelo por Brier score e log loss antes de qualquer otimização automática.

## Referências técnicas

- Py-FSRS: https://github.com/open-spaced-repetition/py-fsrs
- FSRS Algorithm: https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm
- Python asyncio TaskGroup: https://docs.python.org/3.14/library/asyncio-task.html
- SQLite WAL: https://sqlite.org/wal.html
- NASA Software Engineering Handbook: https://standards.nasa.gov/node/182
- NASA-STD-8739.8: https://standards.nasa.gov/standard/NASA/NASA-STD-87398

O QuestFlow não é certificado ou afiliado à NASA. As referências foram usadas como orientação de processo, verificação e confiabilidade.
