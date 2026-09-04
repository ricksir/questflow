# Validação técnica — QuestFlow Studio 6.9.0

## Resultado da validação direcionada

**APROVADO para entrega da Mobile Integration Foundation**, com a ressalva de que a descoberta integral de todos os 93 módulos de teste legados não concluiu dentro da janela do ambiente de execução. Nenhuma falha funcional foi observada antes dos timeouts; por isso, timeout não foi contado como aprovação.

### Blocos confirmados

- **8/8 testes específicos da 6.9.0**: isolamento físico de tenants, sessão estrangeira rejeitada, idempotência, pareamento de uso único, revisão histórica, metacognição, contrato HTTP e painel mobile.
- **43/43 testes críticos**: 6.9.0 + adaptive engine + learning analytics + FSRS + migrações + mobile access + Web API + HTTP local.
- **60/60 testes de hardening/versionamento**: watchdog, tutor, benchmark, comentários Google, production hardening, observabilidade e Quality Gates 6.8.4 preservados.
- **91 testes adicionais avaliados por módulos**: 88 passaram de primeira; 3 apontaram apenas expectativa antiga de `study migration = 11`. Os três testes foram atualizados para a nova migração 12 e os módulos afetados passaram **23/23** na repetição.
- Portanto, **194 testes direcionados tiveram resultado aprovado ao longo dos blocos validados**, sem contar smoke/compile/lock-check.

## Validações de release

- `python -m compileall`: OK.
- `node --check web/app.js`: OK.
- `release_tools.py lock-check`: OK — 8 dependências exatas, SHA-256 válido.
- `release_tools.py smoke`: OK — versão `6.9.0`, compile e `PRAGMA quick_check` aprovados.
- SBOM CycloneDX 1.5: `SBOM_6.9.0.cdx.json` gerado.
- Compatibilidade: Python 3.13 disponível e validado neste ambiente; 3.11/3.12 não estavam instalados para execução local; 3.14 permanece experimental conforme política já existente.
- Auditoria de vulnerabilidades: comando preparado, mas `pip-audit` não está instalado neste ambiente; resultado registrado como `unavailable`, não como “sem vulnerabilidades”.

## Quality Gate do tempo de resposta

A 6.9.0 não usa mais, como sinal confiável de velocidade, a simples diferença entre “abriu questão” e “respondeu”.

Casos automatizados aprovados:

1. questão ficou aberta por **3600 s**, mas o cliente informou **42 s ativos + 3558 s ociosos** → `active_filtered`, 42 s entram na métrica;
2. questão ficou aberta por **4000 s** e só existe wall-clock → `idle_contaminated`, a resposta conta para acerto/erro, mas o tempo fica fora das médias/modelos de velocidade;
3. timer marcado como ativo, mas a questão ficou longa quase sem interação e há evidência de grande intervalo ocioso → velocidade descartada de forma conservadora;
4. dados antigos sem medição ativa → `legacy_unverified`, preservados para auditoria e fora das métricas de velocidade.

A política é deliberadamente conservadora: **quando a qualidade do timing é duvidosa, descarta-se o sinal de velocidade, não a tentativa.**

## Limitação conscientemente não simulada

A release implementa a API, identidade/tenant, pareamento, dispositivos, eventos, snapshots, sync por cursor e projeções. Um **Gateway Cloud permanentemente hospedado + provedor OAuth/OIDC com PKCE + bancos Turso provisionados por usuário** exige infraestrutura/credenciais externas e não foi falsamente marcado como “implantado”. O contrato foi desenhado para esse adaptador posterior.
