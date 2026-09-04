# Validação QuestFlow Studio 2.1.8

## Problemas corrigidos

1. A área de edição não acompanhava a roda do mouse quando o ponteiro estava sobre os campos da questão.
2. A releitura do PDF podia terminar internamente sem que a interface processasse o evento, mantendo o texto “Relendo...” e o botão desabilitado.

## Alterações validadas

- roteamento da roda do mouse para o canvas da área de edição;
- suporte aos eventos `MouseWheel`, `Button-4` e `Button-5`;
- tratamento de `reread_progress`, `reread_done`, `reread_error` e `reread_cancelled`;
- reativação automática dos controles ao finalizar a releitura;
- seleção e recarga da questão atualizada após a releitura;
- botão de cancelamento usando `ExtractionCancelled`;
- caminho completo do PDF salvo nas novas questões importadas.

## Diagnóstico

O diagnóstico local foi executado e concluiu sem falhas, reconhecendo o módulo principal como versão 2.1.8.
