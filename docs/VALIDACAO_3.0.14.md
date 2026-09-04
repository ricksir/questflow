# Validação — QuestFlow Studio 3.0.14

## Escopo

A versão foi validada para quatro alterações principais:

1. retorno seguro ao ciclo das questões corrigidas pelo Telegram;
2. prevenção de envio em massa após iniciar o programa;
3. reinicialização completa do progresso de estudos;
4. prioridade estrita entre questões aprovadas e autoaprovadas.

## Causa identificada para o envio inesperado

O laço de manutenção executava reenvios de entregas sem resposta e falhas antigas antes da verificação de `flow_enabled`. Não havia quarentena de dados legados, limite diário ou limite por sessão. Além disso, entregas antigas da mesma questão podiam continuar elegíveis. Esse conjunto permitia consumir um estoque histórico na reabertura do programa.

## Controles implementados

- ativação da nova política com data de corte;
- bloqueio do estoque anterior à data de corte;
- espera de segurança na inicialização;
- somente a entrega sem resposta mais recente de cada questão;
- limite por lote, sessão e dia;
- retentativas de falhas com lote e sessão limitados;
- ciclo de recuperação respeita a espera inicial;
- preservação do `telegram_update_offset` ao reiniciar o ciclo.

## Fluxo de correção

- solicitação recebida: `suspended=1`;
- correção resolvida: `suspended=0`, `due_at=agora`, `correction_priority=1`;
- seleção: matéria e questão recebem reforço de prioridade;
- entrega bem-sucedida: `correction_priority=0`.

Questões ainda pendentes continuam fora do envio quando o fluxo está configurado para usar somente aprovadas.

## Seleção por status

A seleção busca primeiro `aprovado`/`aprovada`. Se a quantidade for menor que o tamanho solicitado do ciclo, busca o restante em `aprovado_automaticamente` e aliases legados. Questões pendentes permanecem excluídas.

## Testes

- 60 testes automatizados: aprovados;
- migração das novas colunas SQLite: aprovada;
- suspensão e reativação da correção: aprovada;
- prioridade após correção: aprovada;
- quarentena de backlog antigo: aprovada;
- reset preservando correções ativas: aprovado;
- preferência APROVADO → APROVADO_AUTOMATICAMENTE: aprovada;
- teste gráfico com abas, escala e interface: aprovado.

## Limitação do ambiente de construção

O diagnóstico local não carregou `pymupdf4llm` e `selenium` porque esses pacotes não estavam disponíveis no índice Python isolado do ambiente de construção. Eles permanecem no `requirements.txt` e o instalador do Windows tenta instalá-los antes do diagnóstico. Todos os testes que não dependem dessas instalações externas foram concluídos com sucesso.
