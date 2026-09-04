# Validação — QuestFlow Studio 4.2.0

## Escopo

- modularização da interface;
- separação entre consultas e comandos;
- migrações versionadas;
- persistência e medição de calibração;
- regressão do banco, OCR, Telegram e ciclo adaptativo.

## Resultados

| Verificação | Resultado |
|---|---|
| Compilação Python | aprovado |
| Testes automatizados | 98 aprovados |
| Diagnóstico integrado | sem falhas locais |
| Teste gráfico | aprovado |
| Banco antigo e migração idempotente | aprovado |
| Views sem acesso direto ao SQLite | aprovado |
| Snapshot de esquema | gerado |
| Brier score, log loss e ECE | aprovados |
| Benchmark com 5.000 questões | aprovado |

## Benchmark local

```text
Questões importadas: 5000
Importação: 0,347 s
Seleção adaptativa de 20/5000: 0,096 s
Painel agregado: 0,011 s
```

Os tempos variam conforme computador, antivírus, disco e conteúdo real dos documentos.

## Limitações do ambiente de validação

`pymupdf4llm` e `selenium` não estavam disponíveis no ambiente local do diagnóstico. O programa registrou aviso e validou os fallbacks. O instalador do Windows continua responsável por instalar essas dependências quando disponíveis.

A conexão real com o Telegram exige token e Chat ID do usuário e deve ser confirmada pelo botão **Testar bot**.
