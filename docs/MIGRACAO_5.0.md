# Migração para QuestFlow Studio 5.0.0

## Dados preservados

Copie da versão anterior para `data`:

```text
questflow_questions.sqlite
config.json
question_images
markdown_cache
google_browser_profile
```

## Não copiar

```text
.venv
__pycache__
taxonomia_afrfb.json antigo
web da versão anterior
```

## Passos

1. Feche todas as versões do QuestFlow.
2. Extraia a versão 5.0 em uma pasta nova.
3. Copie os dados listados acima.
4. Execute `INSTALAR_E_DIAGNOSTICAR.bat`.
5. Inicie por `INICIAR_QUESTFLOW_STUDIO.bat`.
6. Teste o bot em Configurações antes de reativar o ciclo.

## Fallback

A interface clássica permanece disponível em `INICIAR_INTERFACE_CLASSICA.bat`. Ela usa exatamente o mesmo banco. Não abra as duas interfaces simultaneamente para editar a mesma questão.
