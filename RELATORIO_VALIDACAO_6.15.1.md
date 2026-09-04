# Relatório de validação — QuestFlow Studio 6.15.1

## Correção

A 6.15.0 implementou o núcleo de mesclagem segura e a interface clássica, mas não expôs o painel na interface Web principal usada pelo Studio. A 6.15.1 corrige essa integração visual/HTTP sem alterar o Learning Engine nem o Mobile.

## Validações executadas

- `python -m py_compile web_api.py web_server.py`: aprovado.
- `node --check web/app.js`: aprovado.
- smoke test de release: aprovado; versão carregada 6.15.1.
- testes focados de Web API, interface Web, arquitetura e Course Catalog: **26 aprovados, 0 falhas**.
- teste adicional específico 6.15.1 + Course Catalog: **13 aprovados, 0 falhas**.
- dry-run da Web API confirmado como somente leitura: config e taxonomia não mudam durante o teste.
- aplicação pela Web API preserva progresso existente quando a planilha nova vem vazia e adiciona aula nova como não estudada.

## Suíte completa

A execução monolítica continua sujeita ao problema conhecido de encerramento lento de alguns testes no ambiente Linux de validação. Ao executar arquivos em paralelo sobre o pacote UPDATE sem `data`, um teste legado de integração falhou por ausência proposital de `data/taxonomia_afrfb.json`; isso não representa regressão do hotfix. A validação funcional desta mudança foi feita nos testes diretamente afetados e na simulação de atualização com uma instalação 6.15.0 que contém banco real.

## Banco e Mobile

- Migração nova de banco: nenhuma.
- Alteração destrutiva: nenhuma.
- Mobile: permanece 0.10.1.
- Namespace Cloud Sync para catálogo: `content.*`; Learner State não é reenviado em massa por causa da troca da planilha.
