# Validação técnica — QuestFlow Studio 3.0.2

## Escopo

Esta versão foi validada para os quatro problemas relatados:

1. textos de ajuda cortados na tela de Configurações;
2. botões `A−` e `A+` sem alterar o tamanho das fontes;
3. pesquisa web retornando uma janela vazia e sem opção em lote;
4. processamento apurado que fazia apenas reparo local quando o caminho do PDF não estava disponível.

## Testes automatizados

A suíte `python run_tests.py` executou **24 testes** com sucesso.

Cobertura principal:

- geração de consultas web alternativas;
- parsers de resultados do DuckDuckGo HTML, DuckDuckGo Lite e Bing;
- pontuação por código, banca e similaridade do enunciado;
- aplicação segura de sugestões web;
- localização de PDF por nome quando o caminho antigo não existe;
- integração real da análise apurada: banco pendente → PDF relocalizado → Markdown/OCR → questão Certo/Errado reconstruída;
- extração textual, Certo/Errado, alternativas e gabarito;
- Markdown e liberação do arquivo PDF no Windows;
- repetição adaptativa, estatísticas e falhas do Telegram;
- retentativas e classificação de erros do Telegram.

Resultado completo: `docs/RESULTADO_TESTES_3.0.2.txt`.

## Diagnóstico integrado

O diagnóstico terminou sem falhas e confirmou:

- dependências, Tesseract e taxonomia AFRFB;
- pipeline Markdown/OCR;
- extração e reparo apurado;
- banco e ciclo de estudos;
- retentativas do Telegram;
- três parsers de pesquisa web e consultas alternativas;
- recursos de seleção múltipla, análise em lote e escala da interface;
- consistência da versão 3.0.2.

Resultado: `docs/RESULTADO_DIAGNOSTICO_3.0.2.txt`.

## Teste gráfico

A interface foi aberta em monitor virtual e validou:

- fonte do editor aumentando de **10 para 12 pontos** sem reiniciar;
- tabela de revisão em modo de seleção múltipla;
- botões de pesquisa web em lote e análise selecionada;
- construção de todos os módulos principais sem erro.

Resultado: `docs/RESULTADO_TESTE_INTERFACE_3.0.2.txt`.

## Regressão com PDFs reais

| Documento | Questões | Gabaritos | Certo/Errado | Múltipla escolha | Imagens | Pendentes | Tempo |
|---|---:|---:|---:|---:|---:|---:|---:|
| `tecinformacao1.pdf` | 24 | 24 | 9 | 15 | 2 | 0 | 0,141 s |
| `auditoria8.pdf` | 5 | 5 | 2 | 3 | 0 | 0 | 11,582 s |

Dados completos: `docs/REAL_PDF_REGRESSION_3.0.2.json`.

## Limitações verificáveis

- A conexão real com o Telegram depende do token e do Chat ID e deve ser validada no computador do usuário.
- O ambiente de testes não possuía resolução DNS externa; portanto, a pesquisa web ao vivo não pôde ser executada. Foram testados localmente a geração das consultas, o fallback e os três parsers HTML. Quando não houver resultado automático, o programa oferece abrir a consulta no navegador.
- A análise apurada só consegue reler o documento quando o PDF original é localizado. Agora o programa informa essa condição e permite cadastrar a pasta raiz dos PDFs.
