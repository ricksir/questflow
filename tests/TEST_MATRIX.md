# Matriz de testes QuestFlow Studio 3.0

- Telegram: payload de quiz, conteúdo longo, classificação de erros, backoff e parada em erro permanente.
- Banco/retentativas: migração das colunas, persistência do motivo, início e falha de reenvio.
- Matemática adaptativa: probabilidade bayesiana de erro, recência e intervalo variável.
- Markdown: PDF → Markdown, persistência e cache por hash.
- Extração: lista textual, múltipla escolha, Certo/Errado e gabarito.
- Exportação: base nativa QuestFlow e validação estrutural.
- Enriquecimento: construção da busca, pontuação e aplicação conservadora de sugestões.
- Regressão real: PDFs de Auditoria e Tecnologia da Informação usados na validação externa do pacote.


## Versão 3.0.3

| Área | Cenário | Resultado esperado |
|---|---|---|
| Interface | Aumentar escala no cabeçalho | Fontes explícitas e estilos aumentam imediatamente |
| Interface | Configurações com texto auxiliar em duas linhas | Texto completo, sem sobreposição ou corte vertical |
| Revisão | Selecionar linhas com Ctrl/Shift | Uma ou várias questões ficam selecionadas |
| Pesquisa web | Pesquisar questão atual | Consultas alternativas e resultados de até três provedores |
| Pesquisa web | Pesquisar várias pendentes | Quantidade configurável e resumo por questão |
| Pesquisa web | Provedor muda ou fica indisponível | Próximo provedor é tentado e erros ficam visíveis |
| Análise apurada | Caminho antigo do PDF inválido | Arquivo é localizado pelo nome em pastas configuradas |
| Análise apurada | Processar questão selecionada | Markdown, OCR e imagem são refeitos em DPI alto |
| Análise apurada | PDF não encontrado | Questão permanece pendente com alerta específico |
| Regressão | `tecinformacao1.pdf` | 24 questões, 24 gabaritos e 2 imagens |
| Regressão | `auditoria8.pdf` | 5 questões, 5 gabaritos e 0 pendentes |

| Pesquisa web | Código e enunciado | Confirma identidade e rejeita mesmo código com texto diferente |
| Pesquisa web | Gabarito e alternativas | Transcreve campos ausentes somente em correspondência segura |
| Revisão | Questão anulada | Retira da base ativa, arquiva e bloqueia reimportação |


## Versão 3.0.12

| Área | Cenário | Resultado esperado |
|---|---|---|
| Telegram | Gerar quiz de questão salva | Enquete contém botão **Corrigir esta questão** com identificador inferior a 64 bytes |
| Telegram offline | Clicar enquanto o programa está fechado | Atualização é consumida quando o listener voltar, dentro do prazo do Bot API |
| Persistência | Clicar repetidamente na mesma questão | Uma solicitação ativa é atualizada, sem duplicidade |
| Interface | Receber solicitação com o programa aberto | Aba **Correções Telegram** abre e seleciona a questão recebida |
| Revisão | Abrir solicitação | Questão correspondente é selecionada na aba Revisar banco |
| Revisão | Salvar e aprovar | Solicitações ativas da questão passam para `resolvida` |
| Listener | Ciclo diário desativado | Botões e respostas continuam sendo capturados |


## Reenvio sem resposta e mapa de aulas — 3.0.13

- entrega antiga sem resposta entra na fila;
- entrega respondida é excluída da fila;
- reenvio cria vínculo com o envio anterior;
- callback de correção é persistido e recuperado;
- caixa de saída mantém confirmações com falha;
- cobertura diferencia sem questões, nunca enviada, parcial e completa.
