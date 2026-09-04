# Migração para QuestFlow Studio 4.2.0

## Dados que devem ser copiados

Com o programa fechado, copie da versão anterior para a pasta `data` da 4.2.0:

```text
questflow_questions.sqlite
config.json
question_images
markdown_cache
google_browser_profile
```

Não copie:

```text
.venv
__pycache__
taxonomia_afrfb.json antigo
```

## Primeira abertura

1. Execute `INSTALAR_E_DIAGNOSTICAR.bat`.
2. O programa criará a tabela `schema_migrations`.
3. As colunas novas serão adicionadas de forma idempotente.
4. Nenhuma questão, resposta ou imagem é apagada.
5. Abra `INICIAR_QUESTFLOW_STUDIO.bat`.

## Novos dados de calibração

As tentativas antigas não possuem probabilidade histórica e não são inventadas. Brier score, log loss e ECE começam a ser calculados a partir das novas respostas registradas na versão 4.2.
