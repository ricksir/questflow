# Relatório de validação — QuestFlow Studio 6.17.1

## Escopo

Correção do Tutor IA para permitir edição humana auditável do rascunho, preservar o texto original da IA e detectar quando a questão-base foi alterada em **Revisar banco** após a geração da orientação.

A release final também corrige a migração de orientações antigas para evitar falsos avisos de **questão alterada** causados apenas por `updated_at` técnico do banco.

## Implementação concluída

- rascunho do Tutor editável na interface Web;
- botão **Salvar alterações**;
- texto original da IA preservado em `response_text`;
- versão humana separada em `edited_response_text`;
- histórico de revisões em `qf_ai_response_revisions`;
- nova avaliação independente após cada edição humana;
- snapshot/hash do conteúdo da questão para novas orientações;
- detecção de alteração em enunciado, alternativas, gabarito, explicação, matéria, assunto, aula e código da fonte;
- bloqueio de aprovação de orientação desatualizada também no backend;
- ação **Gerar novamente com a questão atual**;
- auditoria mantém a orientação antiga sem reescrevê-la;
- migração `ai_governance` v6 cria baseline hash seguro para orientações antigas sem snapshot;
- Auditoria identifica explicitamente baseline legado, sem fingir reconstrução histórica exata.

## Testes direcionados e de regressão

Foram executados 124 testes pytest diretamente relacionados ao Tutor IA, Evaluation & Governance Engine, Web API, UI de IA, banco/revisão, migrações, hardening, atualizador Windows, Cloud Sync boundary e Mobile offline boundary.

Resultado: **124 aprovados, 0 falhas**.

Também foram aprovados:

- `node --check web/app.js`;
- smoke test Python da release 6.17.1;
- `compileall` dos módulos críticos;
- Python 3.13.5 disponível no runtime: aprovado.

A tentativa de executar a suíte completa monolítica/particionada neste ambiente não concluiu por travamento já conhecido de alguns testes que iniciam processos auxiliares. Esses testes não são contados como aprovados. A regressão solicitada para os componentes alterados foi executada integralmente.

## Validação em cópia do banco real

Foi utilizada uma cópia do banco com:

- **1.292 questões**;
- 1.292 estados de estudo;
- 18 tentativas Telegram;
- 8 estados de tópico;
- 8 estados de aula;
- 1 estado do modelo adaptativo;
- 1 learner profile;
- **7 interações de IA legadas**, todas anteriores ao suporte a snapshot da questão.

Resultado após aplicar as migrações v5+v6:

- `PRAGMA quick_check = ok`;
- foreign key violations = **0**;
- questões = **1.292 → 1.292**;
- tabelas pedagógicas protegidas mantiveram hash lógico idêntico;
- os 16 campos originais das 7 interações de IA mantiveram hash lógico idêntico;
- 7/7 orientações legadas receberam `legacy_upgrade_baseline_6171`;
- falsos avisos de questão alterada imediatamente após migração = **0**;
- uma alteração real de enunciado feita depois do baseline foi detectada corretamente;
- edição humana em orientação real preservou o texto original e criou revisão auditável.

## Migrações realizadas

`ai_governance` v5:

- `edited_response_text`;
- `edited_at`;
- `edit_note`;
- `question_snapshot_sha256`;
- `question_snapshot_json`;
- `question_updated_at`;
- tabela `qf_ai_response_revisions`.

`ai_governance` v6:

- `question_snapshot_origin`;
- `question_snapshot_captured_at`;
- backfill idempotente do hash/snapshot das orientações legadas.

Não há migração destrutiva.

## Impacto

- Banco: somente alterações aditivas de auditoria do Tutor IA.
- Learning Engine: **sem alteração**.
- FSRS/KT/IRT/Learner State: **sem alteração**.
- Mobile: permanece **0.12.0**, sem alteração.
- Cloud Sync: sem nova tabela sincronizada e sem alteração do fluxo.

## Compatibilidade e segurança

- Python 3.13.5: testado e aprovado.
- Python 3.11/3.12: não disponíveis neste runtime, portanto não marcados como executados aqui.
- Python 3.14: não disponível; permanece experimental/controlado.
- SBOM CycloneDX 1.5: gerado.
- `pip-audit`: não instalado neste runtime; arquivo de auditoria registra `unavailable` em vez de simular sucesso.

## Validação do pacote final

A validação do ZIP final exato pelo atualizador seguro é registrada no arquivo externo `VALIDACAO_FINAL_6.17.1.json`, gerado somente depois do empacotamento final para não alterar o hash do ZIP já testado.
