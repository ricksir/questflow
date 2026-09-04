# Migração do QuestFlow PDF Importer

## Banco compatível

O QuestFlow Studio lê diretamente o arquivo SQLite criado pelo QuestFlow PDF Importer. O arquivo normalmente está em:

```text
QuestFlow_PDF_Importer_...\data\questflow_questions.sqlite
```

## Migração automática

Se o banco do Studio estiver vazio e a pasta antiga estiver ao lado da nova, o programa oferece a migração após abrir.

## Migração manual

1. Abra a aba **Backup e exportação**.
2. Clique em **Migrar banco do PDF Importer (.SQLITE)**.
3. Escolha o banco antigo.
4. Aguarde o resumo.

A migração:

- lê o campo `data_json` de cada questão;
- preserva metadados, classificação e revisão;
- evita duplicatas por código e fingerprint;
- não modifica o arquivo de origem.

## Migração entre computadores

A forma mais completa é copiar toda a pasta `data`. Caso só exista o banco antigo, use o botão de migração e depois atualize a taxonomia na aba **Configurações**.
