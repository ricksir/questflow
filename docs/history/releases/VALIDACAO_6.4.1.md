# Validação técnica — QuestFlow Studio 6.4.1

## Escopo

- Hardening multiprovedor: OpenAI/Gemini `store=false`, compatibilidade de sampling Claude recente e retry exponencial limitado.
- Provedor padrão privacy-first: QuestFlow local/RAG.
- Token do Telegram removido do `config.json` e encaminhado ao cofre DPAPI no Windows.
- Monitor quinzenal consent-first, configurável, assíncrono e sem acesso ao SQLite.
- Versionamento runtime centralizado por `VERSION.txt` e metadados alinhados em 6.4.1.
- Higienização do pacote final.

## Segurança do monitor

O scheduler executa apenas cálculo local de datas. A rede é acessada somente depois da confirmação **Verificar agora**. A consulta é executada como tarefa Python fora da thread da interface. A implementação `core/update_monitor.py` não importa nem abre o repositório SQLite; mantém snapshots e histórico em `update_monitor_state.json`.

Quando todas as fontes falham por ausência de internet/proxy/bloqueio:

- `offline_or_blocked = true`;
- nenhuma janela quinzenal é marcada como concluída;
- a verificação fica disponível para nova tentativa;
- o banco de questões não é tocado.

## Fontes monitoradas

Somente endpoints/páginas first-party configuradas no código:

- OpenAI API changelog e deprecações;
- Google Gemini API release notes;
- Anthropic Claude API release notes;
- documentação Python/sync do Turso;
- Gran Questões;
- Estratégia Sistema de Questões;
- QConcursos;
- TEC Concursos.

## Testes

- Suite completa: **308/308 testes automatizados aprovados**.
- Testes novos 6.4.1 cobrem versão, default local/RAG, `store=false`, compatibilidade Claude, retry, ciclos 1/15, offline, skip/snooze, allowlist HTTP e sanitização do token Telegram.
- JavaScript: `node --check web/app.js` aprovado.
- Python: módulos principais compilados/validados.
- API local: métodos do monitor presentes na allowlist e tarefa iniciada em background.

## Compatibilidade

Nenhuma migração de schema SQLite foi necessária. A 6.4.1 preserva os schemas e os seis motores da 6.4.0; as mudanças desta release são de infraestrutura, segurança, integração e observabilidade externa.
