# Validação — QuestFlow Studio 5.9.0

## Escopo

Etapa 1 da evolução técnica sobre a base 5.8.0: **Curadoria 2.0, deduplicação semântica híbrida, taxonomia em grafo e RAG híbrido offline-first**.

## Alterações estruturais

- `question_bank` migra de v5 para **v6**.
- Novas tabelas:
  - `qf_semantic_signatures`;
  - `qf_knowledge_nodes`;
  - `qf_question_concepts`;
  - `qf_knowledge_edges`;
  - `qf_rag_chunks`.
- `questions` recebe `semantic_version` e `semantic_indexed_at`.
- `question_duplicate_candidates` passa a registrar método e sinais detalhados do cálculo híbrido.
- Vetores dos chunks RAG são pré-indexados para evitar recálculo durante cada consulta.
- Inclusão, edição, reclassificação, exclusão e arquivamento sincronizam os índices derivados.

## Motor híbrido

A deduplicação combina:

1. similaridade textual;
2. assinatura vetorial local;
3. sobreposição da taxonomia;
4. reforço por banca e ano.

O RAG combina:

1. busca lexical;
2. similaridade vetorial;
3. metadados/taxonomia;
4. reranking com reforço por matéria.

O fallback vetorial é determinístico, local e sem dependências adicionais. A interface do índice foi separada para permitir substituir futuramente o vetor local por embeddings externos sem alterar a UI ou o modelo de dados.

## Política de segurança editorial

A similaridade semântica apenas cria candidatos. O QuestFlow **não exclui nem mescla questões automaticamente**. Comentários assistidos por IA permanecem como rascunho até aceite humano.

## Testes automatizados

- **258/258 testes aprovados** na suíte completa.
- Testes específicos 5.9.0: vetor local, deduplicação híbrida, grafo, recuperação RAG, reindexação, limpeza de ativos derivados e controles de interface.
- `node --check web/app.js`: aprovado.
- compilação Python dos módulos principais e `core/*.py`: aprovada.

A suíte emite alguns `ResourceWarning` provenientes de testes legados com conexões/sockets simulados; não houve falha associada.

## Migração real 5.8.0 → 5.9.0

Foi criada uma base temporária usando o **código original 5.8.0**, com duas questões reais de teste, e só depois ela foi aberta pela 5.9.0.

Resultado:

- versões antes: `[1, 2, 3, 4, 5]`;
- versões depois: `[1, 2, 3, 4, 5, 6]`;
- questões antes/depois: **2 / 2**;
- `PRAGMA quick_check`: **ok**;
- violações de chave estrangeira: **0**;
- cobertura do índice semântico: **100%**;
- chunks RAG: **4**;
- nós do grafo: **8**;
- arestas: **7**;
- vínculos questão→conceito: **16**;
- candidato semântico reescrito detectado: **sim**, método `hybrid_local_hashing`;
- coluna de vetor pré-indexado dos chunks: **presente**.

## Compatibilidade

A etapa não altera o algoritmo FSRS, Learning Analytics, Telegram, importação QConcursos/PDF, sincronização Turso ou o histórico de respostas.
