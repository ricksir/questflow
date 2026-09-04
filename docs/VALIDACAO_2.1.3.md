# Validação QuestFlow Studio 2.1.3

## Objetivo
Validar o recorte automático de imagens de questões e o suporte a anexo manual.

## Cenário validado
Arquivo de teste: `tecinformacao1.pdf`.

## Resultado
- 24 questões extraídas;
- 24 gabaritos associados;
- 2 questões com contexto visual identificado (`12` e `16`);
- 2 imagens recortadas automaticamente e salvas em `data/question_images`;
- imagem vinculada ao JSON da questão pelo campo `imagem_questao`;
- módulo Telegram atualizado para enviar a foto antes da enquete;
- tela de revisão preparada para visualização, troca manual e remoção da imagem.

## Observações
Se o PDF não permitir localizar a figura corretamente, a questão permanece utilizável e o usuário pode anexar a imagem manualmente na revisão.
