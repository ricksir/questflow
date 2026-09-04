# Validação QuestFlow Studio 4.0.0

## Resultado geral

- compilação de `app.py` e módulos: aprovada;
- diagnóstico funcional: aprovado sem falhas locais;
- testes automatizados: **77 aprovados**;
- teste gráfico em monitor virtual: aprovado;
- benchmark sintético com 5.000 questões: aprovado.

## Telegram

Foram validados:

- quiz sem explicação comprimida por padrão;
- modo de compatibilidade com explicação nativa;
- cartão HTML completo após a resposta;
- divisão de explicações longas em múltiplas mensagens;
- alternativa escolhida e correta;
- XP, sequência, tempo e retenção prevista;
- botões de explicação, correção, próxima questão e desempenho;
- deduplicação de feedback;
- retentativas, classificação de erros e continuidade offline.

A conexão real depende do token e Chat ID do usuário e deve ser confirmada pelo botão **Testar bot**.

## Motor adaptativo

Foram testados:

- monotonicidade da curva de esquecimento;
- relação entre retenção-alvo e intervalo;
- aumento de estabilidade após acerto;
- redução de estabilidade após erro;
- atualização incremental do modelo;
- prioridade maior para risco e atraso;
- migração de banco anterior;
- painel agregado.

## Interface

- escala ao vivo de fontes;
- Painel adaptativo Mission Control;
- Correções Telegram;
- Mapa de aulas;
- seleção múltipla e processamento em lote;
- painéis redimensionáveis e navegação entre abas.

## Benchmark local

O arquivo `RESULTADO_BENCHMARK_4.0.0.txt` registra o resultado obtido neste ambiente. Tempos variam conforme processador, disco, antivírus e quantidade de histórico.

## Dependências opcionais

`pymupdf4llm` e `selenium` não estavam instalados no ambiente de construção. O diagnóstico confirmou os modos alternativos. No Windows, o instalador tenta instalar essas bibliotecas para habilitar a conversão Markdown avançada e a navegação visível.
