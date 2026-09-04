# Validação técnica — QuestFlow Studio 6.5.1

## Escopo

Release de consolidação do **AI Gateway**, mantendo a arquitetura de seis motores da 6.5.0.

## Resultado automatizado

- **319/319 testes aprovados** (`python -m unittest discover -s tests -p 'test_*.py'`).
- Testes específicos novos: Structured Outputs nos três provedores REST, minimização de dados, prompt injection, migração `ai_governance v3`, telemetria e allowlist/UI.
- `node --check web/app.js`: aprovado.
- Compilação dos módulos Python: aprovada.

## Migração real 6.5.0 → 6.5.1

A base foi criada com o código original 6.5.0, contendo questão e interação de Tutor já persistida, e depois aberta pela 6.5.1.

- Questões preservadas: 1/1.
- Interações de IA preservadas: 1/1.
- `ai_governance`: `[1, 2] → [1, 2, 3]`.
- Tabela nova `qf_ai_provider_metrics`: criada vazia, sem alterar histórico anterior.
- `PRAGMA quick_check`: **ok**.
- `PRAGMA foreign_key_check`: **0 violações**.
- Arquitetura após migração: **6 motores**.

## Structured Outputs

O transporte foi testado com mocks das três APIs, validando os payloads específicos e parsing do objeto retornado:

- OpenAI: JSON Schema em `text.format`, `strict=true`.
- Gemini: JSON Schema em `response_format` com `application/json`.
- Claude: JSON Schema em `output_config.format`.

Se o provedor/modelo não aceitar o schema ou falhar, o Tutor mantém o fallback local fundamentado e registra a falha na governança.

## Prompt injection

O pipeline executa:

`RAG → detectar sinais → classificar como untrusted_data → sanitizar linhas suspeitas → delimitar dados → prompt externo`

O hash SHA-256 do trecho original é mantido no metadado de segurança da fonte para auditoria, sem dar privilégio ao conteúdo original.

## Centro de Privacidade

Modos validados:

- **Privado**: nenhuma informação da questão é enviada a IA externa.
- **Equilibrado**: conteúdo necessário da questão/RAG, sem Learner Model nem anotações pessoais.
- **Personalizado**: seleção granular de campos.

A prévia do Tutor informa os campos compartilhados e não compartilhados antes da geração.

## Telemetria

`ai_governance v3` registra:

- provedor/modelo;
- operação/status;
- latência;
- tokens de entrada/saída/cache;
- Structured Output;
- quantidade de sinais de prompt injection;
- custo estimado quando preços foram configurados pelo usuário.

Nenhuma API key é registrada nessa tabela.
