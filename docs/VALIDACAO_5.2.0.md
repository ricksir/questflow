# Validação técnica — QuestFlow Studio 5.2.0

Data da validação: 06/08/2026.

## Resultado geral

- **120 testes automatizados aprovados** em 5,25 segundos.
- Compilação dos módulos Python concluída sem erro.
- Sintaxe do JavaScript validada pelo Node.js.
- CSS analisado sem erro de parsing.
- Diagnóstico integrado concluído sem falhas locais.
- Motor HTTP/JSON local validado com autenticação por token e bloqueio de métodos não autorizados.

## Desempenho do núcleo

Benchmark local com base temporária de 5.000 questões:

| Operação | Resultado |
|---|---:|
| Importação de 5.000 questões | 0,287 s |
| Seleção adaptativa de 20 questões | 0,091 s |
| Painel agregado | 0,010 s |

Os valores são medições do ambiente de validação e não constituem garantia de tempo idêntico em outro computador.

## Inicialização e isolamento

Foram verificados:

- servidor ligado exclusivamente a `127.0.0.1`;
- token aleatório por abertura;
- comunicação por HTTP/JSON sem depender da injeção da ponte JavaScript;
- Microsoft Edge/Google Chrome em processo visual separado;
- `pywebview` como segunda opção e Tkinter como última alternativa;
- carregamento do núcleo, SQLite e Telegram fora da thread da interface;
- cache do painel para exibição inicial imediata;
- preservação da sessão após F5 sem manter o token na URL.

## Layout e responsividade

As telas **Revisar banco**, **Fluxo Telegram**, **Mapa de aulas** e **Configurações** foram renderizadas em:

- 1566 × 989;
- 1366 × 768;
- 1100 × 800;
- 900 × 700.

Em todas as dimensões verificadas, `scrollWidth` permaneceu igual à largura útil do documento e da área de trabalho, sem vazamento horizontal global. Também foram conferidos:

- quebra controlada de matéria e assunto;
- exibição adaptativa das colunas;
- lista e editor com rolagem independente;
- ações de salvar visíveis em 1366 × 768;
- switches compactos no Fluxo Telegram;
- tabela do Mapa de aulas convertida em cartões rotulados em larguras menores;
- menu lateral recolhido sem sobreposição do conteúdo.

## Comandos executados

```text
python -m pytest -q
python -m compileall -q app.py app_shared.py desktop_runtime.py web_api.py web_server.py core ui
node --check web/app.js
python diagnostico.py
python tests/performance_benchmark.py
```

O teste real de envio exige credenciais válidas do bot e deve ser feito pelo botão **Testar bot** no computador de destino.
