# Validação QuestFlow Studio 3.0.0

Data: 17/07/2026

## Testes automatizados

Resultado: **16 testes aprovados**.

Abrangência:

- payload de quiz e conteúdo longo;
- falha temporária recuperada na terceira tentativa;
- erro permanente interrompido sem repetição inútil;
- classificação local de falhas;
- ciclo de vida de entrega com erro e reenvio;
- probabilidade bayesiana, recência e intervalos adaptativos;
- PDF para Markdown e cache;
- extração de múltipla escolha e Certo/Errado;
- validação da base QuestFlow;
- pesquisa assistida e aplicação segura das sugestões.

## Diagnóstico integrado

Resultado: **sem falhas locais**.

Validou dependências, Tesseract, taxonomia, Markdown, extratores, reparo apurado, banco, ciclo de 20 questões, estatísticas, retentativas, quiz, botões, agendamento e recursos da interface.

## Regressão com PDFs reais

### `tecinformacao1.pdf`

- 24 questões;
- 24 gabaritos;
- 9 questões Certo/Errado;
- 15 de múltipla escolha;
- 2 imagens vinculadas;
- 0 pendentes no resultado de regressão;
- modo textual lista/gabarito.

### `auditoria8.pdf`

- 5 questões;
- 5 gabaritos;
- 2 questões Certo/Errado;
- 3 de múltipla escolha;
- 0 pendentes no resultado de regressão;
- modo OCR/visual.

Os detalhes estão em `REAL_PDF_REGRESSION.json`.

## Teste gráfico sem monitor

A aplicação foi criada em ambiente gráfico virtual e confirmou:

- cinco páginas carregadas;
- dois painéis na revisão;
- dois painéis no fluxo;
- tabela de histórico com motivo e tentativas;
- janela inicial 1360 × 850.

## Limitação da validação

Não foi realizado envio real, pois isso exige o token e o Chat ID particulares. A tela **Testar bot** e o botão de envio devem ser usados no computador do usuário.
