# Relatório de validação — QuestFlow Studio 6.23.1 + Mobile 0.15.6

## Resultado

- Studio: pacote de atualização segura gerado e validado.
- Mobile: APK Android gerado pelo Expo EAS com status `FINISHED`.
- Identidade Android preservada: `br.questflow.mobile`, `versionCode` 21.
- Banco instalado real não foi alterado durante a preparação da entrega.

## Correções verificadas

- O feedback de acerto/erro é retornado antes das projeções FSRS/KT/IRT e analytics.
- As projeções são retomáveis e têm checkpoint durável na outbox/eventos internos.
- A navegação para a próxima questão não aguarda uma sincronização completa.
- Blocos recomendados e por matéria excluem as questões do bloco Mobile anterior.
- Revisão e caderno de erros continuam autorizados a repetir questões por intenção pedagógica.

## Validações executadas

- `release_tools.py ci --full`: aprovado; 134 módulos em quatro partições, sem falhas.
- Teste pytest complementar do catálogo: 12 casos aprovados.
- Testes direcionados do fluxo rápido, projeções e rotação: aprovados.
- TypeScript Mobile (`npm run typecheck`): aprovado.
- Núcleo Mobile (`npm run test:core`): aprovado.
- Compilação Python e smoke test do Studio: aprovados.
- SQLite do ensaio de atualização: `quick_check` aprovado, zero violações de chave estrangeira.
- Atualização ensaiada em cópia isolada de 6.23.0 para 6.23.1, com backup/restauração aprovados e hash do banco preservado.
- APK: contêiner ZIP válido, 1.386 entradas e componentes obrigatórios presentes (`AndroidManifest.xml`, `classes.dex`, `resources.arsc`).

## Artefatos

- `QuestFlow_Studio_6.23.1_UPDATE.zip` — 3.731.977 bytes.
- `QuestFlow_Mobile_0.15.6.apk` — 136.791.801 bytes.
- Evidência sanitizada do build: `EAS_BUILD_MOBILE_0.15.6.json`.
- Checksums: `SHA256SUMS_6.23.1.txt`.

## Observação de segurança

O código Mobile foi enviado ao Expo EAS somente após autorização explícita. O arquivo de envio excluiu dependências locais, cache, artefatos e arquivos `.env`; o build utilizou a credencial Android remota já configurada na conta EAS.
