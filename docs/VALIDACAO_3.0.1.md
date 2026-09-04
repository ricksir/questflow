# Validação técnica — QuestFlow Studio 3.0.1

## Falha corrigida

Na versão 3.0.0, o diagnóstico no Windows podia terminar com:

```text
[FALHA] Pipeline Markdown: [WinError 32] O arquivo já está sendo usado por outro processo
```

A falha ocorria durante a limpeza do PDF temporário usado pelo teste do Pipeline Markdown. A chamada do PyMuPDF4LLM havia retornado, mas um identificador nativo do arquivo ainda podia permanecer aberto por um curto intervalo.

## Solução aplicada

A conversão PyMuPDF4LLM foi movida para `core/markdown_worker.py`, executado como processo auxiliar independente. O processo principal recebe somente o Markdown serializado e as imagens gravadas. Quando o processo auxiliar termina, o sistema operacional libera obrigatoriamente os identificadores do PDF antes da limpeza.

## Testes executados

- compilação de `app.py`, `diagnostico.py` e todos os módulos de `core`;
- diagnóstico integrado completo;
- conversão PDF → Markdown;
- leitura do cache Markdown;
- remoção imediata do PDF após a conversão;
- extração textual e reconhecimento Certo/Errado;
- análise apurada;
- banco, ciclo e estatísticas;
- retentativas e payloads do Telegram;
- agendamento e eventos da interface;
- suíte completa com 17 testes automatizados.

## Resultado

```text
Diagnóstico concluído sem falhas locais.

Ran 17 tests
OK
```

A conexão real com o Telegram continua dependendo do token e do Chat ID configurados pelo usuário.
