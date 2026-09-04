# QuestFlow Studio 6.18.2 — Hotfix de abertura

## Motivo
A versão 6.18.1 removeu acidentalmente funções JavaScript da área de trilhas/estudos que ainda eram chamadas durante `bindEvents()`. A interface HTML aparecia, mas o JavaScript interrompia a inicialização antes de `bridge.startHeartbeat()`, fazendo o runtime exibir que a interface não respondeu.

## Instalação
1. Feche todas as janelas do QuestFlow Studio.
2. Abra o atualizador normal do QuestFlow.
3. Selecione `QuestFlow_Studio_6.18.2_UPDATE.zip`.
4. Conclua o update e inicie o Studio.

Não é necessário apagar `data`, reinstalar o banco ou refazer o pareamento Mobile.

## Impacto
- Banco SQLite: nenhuma migração.
- Learning Engine/FSRS/KT/IRT: nenhuma alteração.
- Mobile: permanece 0.13.1.
- Correções e Matérias não Estudadas: funcionalidades da 6.18.1 preservadas.
