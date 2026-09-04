# Validação QuestFlow 6.9.4 / Mobile 0.2

Escopo: Study Coach mobile, histórico unificado e controle Mobile × Telegram.

## Critérios validados

- contrato `questflow.mobile.v1` preservado;
- campos novos adicionados sem remoção dos campos 6.9.0–6.9.3;
- tela Hoje possui explicação em três etapas: situação, importância e ação;
- Progresso recebe totais de acertos/erros, amostras de tempo, respostas do dia e contagem por canal;
- respostas Mobile, Telegram e Studio são normalizadas no histórico recente;
- tendências recentes e assuntos fracos entram como `insight` por matéria;
- endpoint autenticado permite pausar/retomar somente novas questões do Telegram;
- listener Telegram permanece independente da pausa de questões;
- cliente Mobile atualiza o bootstrap após alterar o canal;
- Quality Gate de tempo ativo permanece obrigatório para velocidade;
- testes Mobile anteriores continuam passando.

## Teste específico da release

Arquivo: `tests/test_mobile_coach_694.py`

Cobre:
1. projeções explicáveis e histórico unificado;
2. separação de tentativas por canal;
3. pausa/retomada do Telegram via Bearer autenticado;
4. presença dos controles e textos orientados à ação no código Mobile 0.2.

## Observação de build

Foi realizada validação sintática TypeScript dos arquivos alterados via TypeScript 5.8.3 (`transpileModule`). A instalação integral das dependências Expo não foi concluída no ambiente de empacotamento por limite operacional do gerenciador de pacotes; por isso o build nativo EAS/Expo deve continuar sendo executado no ambiente de desenvolvimento Mobile, como nas releases anteriores.
