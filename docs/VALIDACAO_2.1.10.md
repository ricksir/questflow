# Validação QuestFlow Studio 2.1.10

## Problema corrigido
Na versão 2.1.9, a thread de análise apurada enviava eventos `deep_progress`, `deep_done`, `deep_cancelled` e `deep_error`, mas a rotina principal da interface não tratava esses eventos. Por isso, a tela permanecia em **0% • Preparando...**, mesmo quando o trabalho ocorria em segundo plano.

## Correções aplicadas
- tratamento de `deep_progress`;
- tratamento de `deep_done`;
- tratamento de `deep_cancelled`;
- tratamento de `deep_error`;
- tratamento de `reread_progress`;
- progresso interno do OCR de cada PDF incorporado ao percentual geral;
- atualização após cada questão;
- reativação dos botões ao concluir, cancelar ou falhar;
- resumo final com processadas, aprovadas, pendentes e relidas.

## Verificações
- módulos Python compilados sem erros;
- diagnóstico local executado;
- versão de `app.py` compatível com `VERSION.txt`.
