# Validação técnica — QuestFlow Studio 6.9.1 + Mobile 0.1 Alpha

Data da validação: **17/08/2026**.

## Resultado

A release foi validada em blocos direcionados, cobrindo a nova superfície mobile e regressões críticas do Studio.

### Testes Python direcionados

- **14/14** — Mobile 0.1 + fundação 6.9.0 + migrações.
- **60/60** — hardening/watchdog, Tutor, benchmark, Google commentary, production hardening e retrieval quality/observability.
- **30/30** — mobile access legado, Cloud Sync, servidor HTTP local e Web API.
- **Total direcionado: 104/104 aprovados.**

Os testes de Cloud Sync/Web API emitiram alguns `ResourceWarning` de conexões SQLite do conjunto legado, mas não houve falha funcional nesse bloco.

### Cliente Mobile

- `npm run test:core`: **OK** usando o núcleo TypeScript de timing/pareamento.
- 21 arquivos `.ts/.tsx` passaram por parsing/transpilação TypeScript para validação sintática.
- `package.json`, `app.json` e `eas.json`: JSON válido.
- O pacote não inclui `node_modules`; o build nativo completo deve ser executado no ambiente de desenvolvimento após `npm install`.

### Cenários de temporização

Simulação automatizada do requisito de tela abandonada:

```text
Questão aberta (wall-clock):  3600 s
Tempo ativo estimado:           42 s
Ociosidade separada:          3558 s
Resultado usado como ativo:     42 s
```

Segundo cenário:

```text
Ativo inicialmente:             10 s
App em background até 1 hora: 3590 s adicionais
Tempo ativo final:               10 s
```

O cliente para de acumular após **60 s sem interação**, mesmo se continuar em foreground. O servidor mantém um segundo Quality Gate e pode excluir amostras de velocidade duvidosas sem invalidar a tentativa pedagógica.

### Release/segurança

- `python -m compileall`: OK.
- `node --check web/app.js`: OK.
- `release_tools.py lock-check`: OK; SHA-256 do lock confere.
- `release_tools.py smoke`: OK; versão 6.9.1 reconhecida e banco com `quick_check=ok`, sem violações de foreign key.
- SBOM CycloneDX: `SBOM_6.9.1.cdx.json`, incluindo dependências Python fixadas e dependências declaradas do Mobile.
- Auditoria Python: ferramenta `pip-audit` indisponível neste ambiente; isso está registrado em `AUDITORIA_VULNERABILIDADES_6.9.1.json` e não foi tratado como auditoria concluída.
- Auditoria npm: não executada porque `node_modules/package-lock.json` não são incluídos no pacote-fonte; executar após `npm install` no ambiente de build.
- Compatibilidade detectada neste ambiente: Python 3.13 disponível; 3.11/3.12/3.14 não instalados localmente para execução nesta sessão.

## Cenários mobile cobertos

- saúde pública mínima da Mobile API sem abrir projeções privadas;
- projeções exigem Bearer;
- pareamento de uso único;
- endereço da API local transportado no QR sem chave administrativa;
- sessão/dispositivo independente;
- isolamento de tenant;
- evento idempotente;
- evento persistido com erro pode ser reprocessado somente se permanecer imutável;
- `question_revision` preserva o gabarito realmente apresentado;
- confiança/dificuldade registradas antes do feedback;
- cache local não armazena gabarito antes da tentativa;
- resposta offline vai para outbox persistente;
- gabarito/explicação aguardam sincronização real;
- timing separa wall-clock, atividade e ociosidade;
- revogação do dispositivo e limpeza local;
- push é opt-in por aparelho.

## Limites conhecidos do Alpha 0.1

1. A conectividade principal é **LAN → QuestFlow Studio**. O computador precisa estar acessível durante a sincronização.
2. OAuth/OIDC + PKCE e Gateway Cloud ainda não estão implantados; são a próxima evolução arquitetônica.
3. Não foi produzido APK/IPA nesta sessão. O pacote contém o projeto mobile completo para instalação das dependências e execução/build em ambiente Expo.
4. Push remoto depende das credenciais/configurações nativas do ambiente de build e de aparelho físico; a API e o registro opt-in já estão preparados.

Esses limites são deliberados: a release não simula infraestrutura externa ou credenciais que ainda não existem.
