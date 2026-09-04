# Segurança e confiabilidade

- Tokens do Telegram e chaves de IA/Turso/proxy são mantidos fora do `config.json`; no Windows, os segredos suportados usam DPAPI vinculado ao usuário atual.
- O programa não envia o banco de questões para servidores próprios.
- OCR, classificação, FSRS, estatísticas e gamificação funcionam localmente.
- A pesquisa Google é opcional e depende do navegador do usuário.
- O botão de reinício do ciclo exige confirmação explícita.
- Filas de Telegram usam identificadores idempotentes para evitar duplicações.
- A gamificação não usa sorteio, compras, apostas, ranking público ou penalidade por ausência.

Relate problemas incluindo versão, trecho do log e passos de reprodução. Nunca envie o token do bot em capturas públicas.


## Proxy corporativo (5.3.1)

A interface principal é servida somente em `127.0.0.1` e permanece fora do proxy. O tráfego externo é centralizado em `core/network.py`. Senhas de proxy manual são armazenadas separadamente de `config.json` e, no Windows, protegidas com DPAPI para o usuário atual. Logs e respostas públicas da API nunca incluem a senha.

## Turso Cloud Sync (5.4.0)

- O token Turso é segredo local e não é sincronizado.
- No Windows o token é protegido pelo DPAPI do usuário atual.
- A API web local nunca devolve o token.
- O transporte ao Turso usa HTTPS/SQL-over-HTTP e respeita o NetworkManager/proxy.
- Eventos remotos carregam SHA-256 de integridade e `event_id` idempotente.
- O acesso móvel LAN fica desativado por padrão e a API exige token aleatório de sessão.
- Não exponha a porta móvel na Internet/NAT; ela foi criada para LAN/VPN confiável.
- Cloud Sync não substitui backup local/versionado.

## AI Gateway e RAG (6.5.1)

- O provedor padrão continua sendo QuestFlow local/RAG.
- O Centro de Privacidade define quais campos podem sair do computador quando uma IA externa é escolhida.
- PDFs, RAG, legislação e resultados externos são tratados como **dados não confiáveis**, nunca como instruções privilegiadas.
- O AI Gateway detecta padrões de prompt injection e sanitiza linhas suspeitas antes do envio a provedores externos.
- OpenAI/Gemini permanecem em modo stateless quando suportado pela API utilizada.
- Saídas externas estruturadas continuam como rascunho e não podem se autoaprovar; a decisão humana pertence ao Evaluation & Governance Engine.
- Telemetria registra desempenho/tokens, mas não armazena API keys.
