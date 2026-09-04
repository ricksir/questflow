# Relatório de validação — QuestFlow Studio 6.21.0 + Mobile 0.14.0

## Escopo implementado

- 15 rotas do Studio reorganizadas por decisão, diagnóstico e detalhe.
- Grid responsivo por rota, rails úteis e módulos sem dependência global de `.panel--wide`.
- Gráficos acessíveis no Painel visual, Visão geral, Curadoria, Importação, Correções, Estudos e integrações.
- Fila + workspace do Tutor, recomendador + rail sticky e geração + validação temporal/quality gates.
- Configurações por subnavegação, salvamento sticky e somente a seção ativa exposta ao DOM interativo.
- Registro central de ações por `data-action`, ciclo de estados de painel e eventos `questflow:*`.
- Mobile com jornadas Hoje, Questões, Progresso, Perfil e Pareamento; gráficos SVG com resumo textual.
- Contrato `AnalyticsSnapshotV2` derivado somente de tentativas e eventos existentes, com intervalo de Wilson e fallback de amostra insuficiente.

## Resultados automatizados

- Suíte Python integral: **604/604 testes aprovados** em quatro partições; uma partição foi repetida sem contenção após um timeout de 10 s do teste de dashboard e concluiu 155/155.
- `npm run typecheck`: aprovado.
- `npm run test:core`: aprovado.
- Expo Doctor: 21/21 verificações aprovadas.
- Testes focados da release `tests/test_questflow_621.py`: 5 aprovados.
- Testes Mobile/adaptativos relacionados: 57 aprovados após correção do lock SQLite no Windows.
- `node --check web/questflow621.js`: aprovado.
- `py_compile`/smoke dos módulos alterados: aprovado.
- EAS Android: build `aac64890-6083-4d30-85d0-b3c183461507` finalizado, app `0.14.0`, versionCode `14`, SDK Expo `57.0.0`.
- Smoke do APK: arquivo ZIP/APK legível, `classes.dex` e bibliotecas nativas `arm64-v8a` presentes. Não havia ADB/emulador no ambiente para instalação física.
- Atualização limpa simulada de 6.18.2 para 6.21.0: hash conferido, backup e `quick_check` aprovados, smoke pós-instalação aprovado, teste de restauração aprovado e `rollback_performed: false`.

## Regressão visual e responsividade

- As 15 rotas do Studio foram abertas a 1440×900, com rota ativa, faixa de ações e ausência de overflow horizontal.
- Visão geral, Tutor, Curadoria, Recomendador, Geração e Fluxo Telegram foram inspecionados a 1920×1080.
- Mobile foi exercitado a 360×800, 390×844, 412×915 e tablet de 768 px, sem overflow horizontal.
- As capturas entregues cobrem Visão geral, Painel visual, Tutor, Recomendador e as cinco jornadas Mobile.

## Dados e segurança

- Nenhuma tentativa, resposta ou questão foi criada para preencher gráficos de produção.
- Séries temporais insuficientes exibem KPI/inclinação e a mensagem de amostra insuficiente.
- `/api/v1/mobile/progress` e os tipos v1 permanecem compatíveis.
- A alteração de banco é aditiva; o pacote exclui dados locais e o atualizador preserva, verifica e pode restaurar o banco.
- Cor não é o único canal: estados possuem texto/ícone, gráficos têm rótulo acessível e resumo equivalente.
- `npm audit --omit=dev`: 0 críticas, 0 baixas, 10 moderadas e 4 altas, todas transitivas da cadeia Expo/Metro de build. O reparo automático sugerido implicaria downgrade principal incompatível do Expo; não foi aplicado à build validada. A atualização coordenada de Expo/Metro fica registrada como dívida de dependência.

## Artefato Android

- Identificador: `br.questflow.mobile`.
- EAS: `https://expo.dev/accounts/rick_sir/projects/questflow-mobile/builds/aac64890-6083-4d30-85d0-b3c183461507`.
- Perfil: `preview`, distribuição interna, APK instalável.
- Fingerprint: `9a45ce1e4d347479ea453a4eb4975420565ad6e1`.

## Evidência de QA

As capturas PNG, o pacote de atualização, o código-fonte, o APK e `CHECKSUMS_SHA256.txt` acompanham este relatório no diretório de entrega.
