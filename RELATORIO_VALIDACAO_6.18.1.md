# Relatório de validação — QuestFlow 6.18.1 / Mobile 0.13.1

## Escopo

- Renomeação da aba para **Correções e Matérias não Estudadas**.
- Separação em duas áreas independentes.
- Compatibilidade da API de correções preservada.
- Resumo de sessão offline sem traço ambíguo.
- Contagem explícita de respostas aguardando correção do Studio.

## Testes executados antes do empacotamento

- 21 testes direcionados: aprovados.
- 62 testes de regressão/arquitetura: aprovados.
- Total pytest desta validação: **83 aprovados, 0 falhas**.
- `node --check web/app.js`: aprovado.
- TypeScript Mobile `--noEmit`: aprovado.
- Mobile `npm run test:core`: aprovado.
- SBOM: gerado.
- Matriz de compatibilidade: Python 3.13.5 disponível e smoke aprovado; 3.11/3.12/3.14 não disponíveis neste ambiente.
- Auditoria de vulnerabilidades: `pip-audit` indisponível no ambiente; status registrado como `unavailable`, sem falsa aprovação.

## Banco

Não há migração de banco nesta versão. A prova final do ZIP registra quantidade de questões, SHA-256 do SQLite, `quick_check` e foreign keys antes/depois.

## Impacto

- Learning Engine: nenhum.
- FSRS/KT/IRT: nenhum.
- Cloud Sync: nenhum.
- Mobile: atualização real para 0.13.1.
