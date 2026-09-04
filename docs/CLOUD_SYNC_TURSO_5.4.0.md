# QuestFlow Studio 5.4.0 — Cloud Sync com Turso

## Objetivo

A versão 5.4.0 mantém o banco principal **local em SQLite** e usa o **Turso Cloud como ponto de troca durável** entre as instalações do QuestFlow. Os computadores não precisam estar ligados ao mesmo tempo. Cada alteração confirmada no SQLite local é registrada em uma fila (`qf_sync_outbox`) dentro da mesma transação e pode ser enviada quando houver Internet.

A implementação não substitui o banco do QuestFlow por um driver remoto. Isso preserva compatibilidade com backup, OCR, importação, reparo, exportação, Telegram e funcionamento offline. O transporte para o Turso usa o endpoint SQL-over-HTTP do próprio Turso e, por isso, passa pelo mesmo **Gerenciador de Rede e Proxy** do QuestFlow.

## Componentes

- `core/cloud_sync.py`: outbox/inbox, replicação, conflitos, geração global e cliente Turso.
- `core/secure_store.py`: proteção do token com DPAPI no Windows.
- `CONFIGURAR_TURSO_CLOUD.bat`: configurador gráfico do QuestFlow.
- `INSTALAR_TURSO_CLI_WSL.bat`: instalador opcional do CLI Turso no WSL.
- `VALIDAR_CLOUD_SYNC.bat`: testes de falha, offline, crash, dois dispositivos e acesso móvel.

## Instalação inicial do Turso no Windows

O runtime do QuestFlow **não exige o Turso CLI**. O CLI é necessário somente para criar/administrar o banco se você não fizer isso pelo painel web do Turso.

No Windows, o CLI oficial utiliza WSL. Em PowerShell como administrador, se ainda não tiver WSL:

```powershell
wsl --install
```

Depois, dentro do WSL:

```bash
curl -sSfL https://get.tur.so/install.sh | bash
exec $SHELL -l
turso auth login
turso db create questflow
turso db show questflow --http-url
turso db tokens create questflow
```

Copie a URL HTTPS e o token. No Windows execute `CONFIGURAR_TURSO_CLOUD.bat` e cole os dois valores.

## Primeiro computador

1. Faça backup do banco atual.
2. Configure URL e token.
3. Nomeie o dispositivo, por exemplo **CASA**.
4. Ative Cloud Sync e salve.
5. Clique **Testar Turso**.
6. Clique **Usar este computador como origem** se este for o banco que deve popular a nuvem inicialmente.
7. Clique **Sincronizar agora** e confirme que `Pendentes = 0`.

## Segundo computador

1. Instale a mesma versão 5.4.0.
2. Configure a mesma URL e token.
3. Use outro nome, por exemplo **TRABALHO**.
4. Ative Cloud Sync.
5. Use **Mesclar com a nuvem**. Não use um banco antigo como “origem” se a nuvem já tiver dados válidos.
6. Sincronize e confirme os dados.

## Proxy corporativo

O Chrome principal continua usando apenas `127.0.0.1`, sem proxy. Somente a saída para Turso/Telegram/Google usa o `NetworkManager`. Assim, o PC de casa pode usar conexão direta e o PC do trabalho pode usar proxy manual, Windows, PAC/WPAD ou autenticação corporativa sem um sobrescrever a configuração do outro.

O token Turso é local ao dispositivo e não é sincronizado. No Windows ele fica protegido por DPAPI e não aparece no `config.json`.

## Comportamento offline

- Todas as leituras e gravações do QuestFlow continuam locais.
- Uma falha de Internet não cancela a transação já salva.
- A alteração fica no `qf_sync_outbox`.
- Quando a rede volta, o serviço em segundo plano tenta novamente.
- A sincronização também ocorre ao abrir e, de forma best-effort, ao fechar.

## Desligamento abrupto

O banco usa WAL e a fila de sincronização é transacional. Se o processo for encerrado depois de um commit local, o evento permanece no outbox. Se a conexão cair depois de o Turso aceitar o evento, mas antes do QuestFlow receber a confirmação, o mesmo `event_id` é reenviado e a nuvem ignora a duplicata (`UNIQUE(event_id)`).

Se o processo morrer **no meio de uma transação local ainda não confirmada**, o SQLite desfaz aquela transação ao reabrir. Isso evita publicar um estado que nunca foi confirmado localmente.

## Conflitos entre dois PCs offline

Quando os dois dispositivos alteram o mesmo registro sem se verem:

1. o primeiro a sincronizar publica sua versão;
2. quando o segundo sincroniza, o QuestFlow detecta que existe uma alteração local pendente para a mesma chave;
3. a alteração local não é sobrescrita durante o pull;
4. o conflito é gravado em `qf_sync_conflicts`;
5. a alteração local é enviada em seguida;
6. o último push passa a ser o estado convergente dos demais dispositivos.

Para dados de estudo, a maior parte do histórico é modelada por registros/eventos próprios, reduzindo colisões em um único contador.

## Reiniciar estudos do zero em ambiente sincronizado

O reset incrementa uma **geração global** antes de limpar o progresso. Um computador que estava desligado com eventos antigos detecta a geração mais nova antes de enviar sua fila e descarta eventos de gerações anteriores. Assim o histórico antigo não “ressuscita” após o reset.

## Acesso pelo celular

A versão 5.4.0 inclui um modo **LAN móvel**, desativado por padrão. Ao ativar em Configurações → Cloud Sync e reiniciar o QuestFlow, o servidor local pode ouvir na rede local e exibe um endereço para abrir no navegador do celular.

Regras de segurança:

- funciona somente enquanto aquele computador estiver com o QuestFlow aberto;
- o celular deve conseguir alcançar o computador pela mesma LAN/VPN;
- a API continua exigindo um token aleatório por sessão;
- não é publicado nenhum token Turso no JavaScript do celular;
- redes corporativas com isolamento de clientes ou firewall podem bloquear esse acesso.

**Importante:** o Turso é banco/sincronização, não um serviço de hospedagem web do QuestFlow. A versão 5.4.0 não expõe um token de escrita do Turso diretamente em uma página pública para permitir acesso remoto com todos os PCs desligados. Isso exigiria um backend hospedado com autenticação própria. No celular, o Telegram continua sendo o canal remoto principal para responder questões.

## Dados sincronizados

Sincronizados: questões, questões excluídas, importações, histórico de código, estado de estudo, entregas/tentativas, ciclos, pedidos de correção, modelo adaptativo, estado por tópico, eventos de XP e perfil do aluno.

Mantidos locais por segurança/operação: fila de callbacks do Telegram, outbox operacional do Telegram, `flow_runtime`, token do Telegram, token Turso, senha/proxy, perfil do Chrome, cache e logs.

## Recuperação

Cloud Sync não substitui backup. Mantenha os backups automáticos do QuestFlow. Antes de qualquer migração ou reset, o banco local continua sendo a fonte imediata de recuperação.
