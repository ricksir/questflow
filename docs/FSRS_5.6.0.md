# Motor de memória 5.6.0

O QuestFlow usa Py-FSRS 6 como scheduler primário. O DSR local existe apenas como continuidade de emergência.

## Pipeline

Planilha estudada → escopo matéria/aula → correções/relearning/vencidas/novas → risco Matéria/Aula/Assunto → interleaving ponderado → Telegram → resposta → metacognição → ReviewLog FSRS → nova due date.

## Otimização

A partir de histórico suficiente, o programa reconstrói ReviewLogs, executa o Optimizer, persiste os 21 parâmetros e a retenção calculada e reagenda os cartões. Novas otimizações automáticas são disparadas após crescimento relevante do histórico.

## Metacognição

Acerto objetivo continua sendo o sinal principal. `Sabia`, `Dúvida` e `Chutei` ajustam Good/Hard/Easy. Erro permanece Again; o tipo de erro é armazenado para diagnóstico.

## Prova e carga

A data da prova limita o horizonte de agendamento. O tempo diário e o tempo médio de resposta geram uma capacidade aproximada e uma recomendação diária, sem alterar silenciosamente o banco.

## Retrievability na seleção

A seleção em lote usa a própria `Scheduler.get_card_retrievability()` do Py-FSRS para cartões já inicializados. O Scheduler é reutilizado para todo o lote, evitando instanciar um scheduler por questão; a curva local só é fallback para registros legados ainda sem cartão FSRS.

O tempo de resposta também é gravado em `ReviewLog.review_duration` (milissegundos), preservando mais informação do histórico oficial para auditoria e otimização.
