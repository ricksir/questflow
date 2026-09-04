# Relatório de validação — QuestFlow Studio 6.15.2

## Problema corrigido

Após um UPDATE, o Manager encerrava o processo Python do QuestFlow, porém não encerrava explicitamente o Chrome que usa o perfil privado do Studio. Esse Chrome podia permanecer órfão e capturar/reutilizar a próxima abertura com `--user-data-dir`, enquanto o novo motor local aguardava um heartbeat que nunca chegava. Ao fechar tudo e abrir novamente, o perfil era liberado e o Studio funcionava.

## Implementação

1. `questflow_manager.ps1`: detecção e encerramento somente de `chrome.exe` cuja linha de comando contém `data\\chrome_runtime_5_4_0` da instalação atual; espera curta pela liberação do perfil.
2. `desktop_runtime.py`: preflight TCP do servidor loopback antes do Chrome.
3. `desktop_runtime.py`: limpeza defensiva de Chrome órfão usando o perfil privado QuestFlow.
4. `desktop_runtime.py`: segunda tentativa automática de abertura quando não há heartbeat.
5. `app.py`: mensagem final de erro só aparece depois das tentativas automáticas.

## Validações executadas

- `py_compile` de `app.py` e `desktop_runtime.py`: aprovado.
- testes específicos do hotfix + runtime Chrome + Manager + recuperação de órfãos + runtime Windows curto: **21 aprovados, 0 falhas**.
- regressão de startup, watchdog, update seguro, hardening, Google commentary e tutor: **43 aprovados, 0 falhas**; duas referências de nome de teste inválidas no comando original foram corrigidas e não eram falhas do código.
- Course Catalog Safe Merge + painel Web 6.15.1: **13 aprovados, 0 falhas**.
- total direcionado contabilizado: **77 testes aprovados, 0 falhas funcionais**.
- smoke test de release: aprovado; `APP_VERSION=6.15.2`.
- Python disponível no ambiente: **3.13.5**, smoke aprovado.
- Python 3.11/3.12/3.14: não disponíveis neste ambiente.
- `pip-audit`: indisponível no ambiente; SBOM gerado normalmente.

## Suíte completa

A suíte monolítica continua sujeita ao problema conhecido de encerramento lento/timeout no ambiente Linux de validação. Depois de disponibilizar os fixtures `mobile/package.json` e `data/taxonomia_afrfb.json` exigidos por testes legados, a execução chegou a aproximadamente 24% sem novas falhas antes do limite do ambiente. A alteração desta release é restrita ao startup Windows/Chrome e foi coberta pelos testes diretamente afetados.

## Limitação de validação

A manipulação real de processos `chrome.exe` via CIM/PowerShell é específica do Windows. Neste ambiente Linux, essa parte foi validada por testes com mocks e inspeção do comando, garantindo que o alvo é o perfil privado do QuestFlow e que não existe `taskkill`/`Stop-Process -Name chrome` genérico. A confirmação definitiva do sintoma específico de primeira abertura ocorre no computador Windows do usuário após instalar o hotfix.

## Impactos

- migração de banco: **nenhuma**;
- impacto no Learner State: **nenhum**;
- impacto no Course Catalog: **nenhum**;
- impacto no Mobile: **nenhum; permanece 0.10.1**;
- impacto no Cloud Sync/Turso: **nenhum**;
- risco destrutivo: **não identificado**;
- Chrome normal do usuário: **não deve ser encerrado**; o filtro usa somente o perfil privado do QuestFlow.
