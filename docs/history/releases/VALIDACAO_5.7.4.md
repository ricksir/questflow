# Validação — QuestFlow Studio 5.7.4

## Correção principal
A 5.7.3 alterou corretamente o dashboard, mas o diagnóstico ainda procurava literalmente o texto legado **“Por que esta prioridade e onde focar”**. Isso provocava uma falha falsa e impedia o instalador de concluir.

A 5.7.4 atualiza o diagnóstico para validar a estrutura real atual:
- `Retenção estimada hoje`;
- `Desempenho recente`;
- resumo compacto `subject-summary-toggle`;
- `renderVisualAnalyticsPanel`;
- `openSubjectAnalyticsModal`;
- rota lateral `visualanalytics`;
- página dedicada do painel visual;
- container `visualAnalyticsPanel`.

Também foi atualizado um teste legado da interface que ainda esperava o antigo `subject-priority-badge`.

## Verificações
- Teste específico Learning Analytics: **9/9 aprovados**.
- Suíte completa: **248/248 aprovados**.
- `node --check web/app.js`: **OK**.
- `python3 -m compileall -q .`: **OK**.
- Diagnóstico local da interface: **[OK] Learning Analytics 5.7.4: resumo compacto, painel visual lateral e drill-down interativo**.

## Observação sobre o ambiente de construção
Neste ambiente Linux de montagem, o diagnóstico geral ainda reporta ausência externa de `fsrs[optimizer]`. Isso é uma limitação do ambiente de construção. No computador do usuário, o print anterior já confirmou que o runtime compartilhado `%LOCALAPPDATA%\QFS\venv` possui Py-FSRS + Optimizer instalados.
