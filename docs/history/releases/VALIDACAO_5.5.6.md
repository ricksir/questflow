# QuestFlow Studio 5.5.6 — Validação

## Agrupamento dos estudos

A cobertura passa a trabalhar, na interface, com a unidade **trilha + matéria + aula**. As tarefas detalhadas do CICLO_REG continuam preservadas na taxonomia e no relatório interno.

Com o snapshot empacotado da planilha, a análise encontrou **40 tarefas estudadas**, consolidadas em **20 grupos de aula**. Exemplo: `TRILHA 0 + AUDITORIA + Aula 00` possui 3 tarefas/partes e passa a aparecer como uma única linha para importação.

A importação contextual de grupo grava `contexto_group_id` e `contexto_task_ids`, força matéria/aula corretas e mantém os assuntos finos extraídos do PDF. A cobertura reconhece essa associação e conta cada questão uma única vez.

## Certo / Errado

O formato de questão foi centralizado em `core/question_types.py`. Para `certo_errado`, as únicas alternativas válidas e persistidas são:

- C — Certo
- E — Errado

O editor troca o layout imediatamente. A abertura de registros legados normaliza A-E apenas para C/E e o Telegram aplica a mesma proteção antes de montar o quiz.

## Testes

- Suíte completa: **226 testes executados / 226 aprovados**.
- 5 testes novos da 5.5.6 cobrem agrupamento, importação por aula, contagem única, conversão Certo/Errado, compatibilidade legada e interface.
