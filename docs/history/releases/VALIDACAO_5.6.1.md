# QuestFlow Studio 5.6.1 — Validação PyMuPDF

Objetivo: eliminar o uso da API legada `fitz` e utilizar diretamente `import pymupdf`.

Verificações realizadas:
- busca em todos os arquivos Python ativos sem ocorrências de `import fitz` ou `fitz.`;
- compilação dos módulos Python;
- testes do extrator, pipeline Markdown, QConcursos e PDFs de trilhas;
- abertura/criação de PDF por `pymupdf.open()`;
- instalador e diagnóstico verificando o módulo `pymupdf`.

Esta atualização não altera schema do banco, scheduler FSRS ou dados do usuário.
