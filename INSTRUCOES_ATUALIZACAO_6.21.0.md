# QuestFlow Studio 6.21.0 + Mobile 0.14.0

## Antes de atualizar

1. Feche o QuestFlow Studio e o Metro/Expo do Mobile.
2. Copie o pacote para uma pasta local com caminho curto.
3. Confirme o SHA-256 publicado em `CHECKSUMS_SHA256.txt`.

## Atualização segura a partir do Studio 6.18.2

Use o atualizador externo já instalado:

```powershell
python release_tools.py update QuestFlow_Studio_6.21.0_UPDATE.zip --install-root "C:\caminho\QuestFlow" --sha256 SHA256_PUBLICADO
```

O atualizador cria e testa um backup prévio, extrai o pacote em staging, executa smoke test, preserva `data`, `.venv`, `runtime` e `backups`, valida o SQLite com `quick_check` e restaura o código anterior se qualquer verificação falhar.

O manifesto desta versão declara `mobile_changed: true`: o código do Mobile 0.14.0 faz parte do pacote e não está em `preserves` nem em `excludes`.

## APK Android

Instale `QuestFlow_Mobile_0.14.0.apk` no aparelho autorizado. O Android pode solicitar permissão para instalar apps da origem usada para abrir o arquivo. Depois da instalação, abra **Perfil** e confirme `Mobile 0.14.0`, então refaça o pareamento se a sessão local não tiver sido preservada.

## Verificação pós-atualização

- O cabeçalho do Studio deve mostrar `6.21.0`.
- O Perfil do Mobile deve mostrar `0.14.0` e build `14`.
- A Visão geral deve carregar KPIs, tendência e prioridades sem overflow horizontal.
- O endpoint `/api/v1/mobile/analytics?range=12w&grain=week` deve responder com `summary`, `timeline`, `subjects`, `priority_breakdown`, `projection_band`, `review_queue`, `sample_size`, `generated_at` e `source_freshness`.
- O banco existente deve permanecer no diretório `data` sem alteração destrutiva.

## Rollback

Em falha durante a aplicação, o atualizador executa rollback automático do código. O banco permanece no local; o backup pré-update fica em `QuestFlow_Backups` ao lado da instalação (ou na pasta temporária do usuário quando necessário).

