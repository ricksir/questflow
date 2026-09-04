# QuestFlow — instruções do projeto

## Escopo e fonte canônica

- Esta pasta é a fonte de desenvolvimento do QuestFlow Studio e do QuestFlow Mobile.
- A instalação em `C:\Users\user\QuestFlow` é destino de implantação. Não a edite diretamente, salvo pedido explícito do usuário.
- Leia `VERSION.txt` e `mobile/package.json` antes de informar ou alterar versões. Não mantenha números de versão duplicados manualmente quando puder derivá-los dessas fontes.
- As instruções explícitas do usuário prevalecem sobre estas convenções.

## Antes de alterar código

- Reproduza ou localize a causa do comportamento pedido. Não conclua apenas pela captura de tela.
- Procure implementações e testes existentes antes de criar outra camada, listener, endpoint ou componente.
- Preserve alterações do usuário e mudanças não relacionadas já presentes na árvore.
- Diferencie diagnóstico de implementação: quando o usuário pedir correção ou construção, implemente e valide; quando pedir apenas análise, não gere release nem altere estado externo.

## Invariantes de dados e integração

- Preserve banco SQLite, respostas, tentativas, progresso, FSRS, Knowledge Tracing, IRT, catálogo, credenciais, pareamentos, fila offline, configurações e backups.
- Migrações de banco devem ser aditivas, idempotentes, testadas e compatíveis com atualização de uma instalação existente.
- Nunca invente tentativas, histórico, métricas ou séries temporais para preencher a interface.
- Studio é a fonte de inteligência e curadoria; Mobile consome contratos públicos e não acessa tabelas internas diretamente.
- Sincronização deve ser idempotente. Recarregar uma tela não pode recriar eventos já confirmados.
- Nunca inclua dados reais, credenciais, tokens, bancos, backups, `.env`, keystores ou arquivos de serviço do Google em commits ou pacotes.

## Implementação

- Faça a menor mudança coerente que resolva a causa raiz e mantenha o comportamento adjacente.
- Reutilize componentes, tokens visuais, serviços e contratos existentes.
- Centralize versões e textos derivados para evitar divergências entre Studio, QR, toast, manifesto e Mobile.
- Mantenha acessibilidade por teclado, foco visível, rótulos, resumo textual de gráficos e ausência de overflow horizontal.
- Para tarefas de release, atualização, ZIP, APK ou incremento de versão, use a skill `questflow-release` em `.agents/skills/questflow-release/`.

## Validação proporcional ao risco

- Toda correção de bug deve ter teste de regressão quando houver uma fronteira testável.
- Rode primeiro os testes diretamente relacionados; antes de uma release, execute os gates aplicáveis descritos na skill `questflow-release`.
- Não declare que um teste, build, APK, instalação ou smoke test passou se ele não foi realmente executado.
- Registre falhas ambientais separadamente de falhas do produto.

## Releases e artefatos

- Não incremente versão nem gere pacote em uma alteração comum, salvo quando o usuário pedir uma release/atualização ou isso fizer parte explícita da entrega.
- Por padrão, grave artefatos distribuíveis fora da fonte, em `../outputs/`.
- Um pacote do Studio deve excluir `data`, `.venv`, `venv`, `runtime`, `backups`, `work`, `node_modules`, caches, repositórios Git e segredos.
- Gere APK somente quando o Mobile mudar ou quando o usuário solicitar explicitamente um novo build.
- Toda entrega de release deve informar versões, arquivos produzidos, checksum, testes executados, limitações e procedimento de rollback.

## Comunicação

- Responda ao usuário em português claro.
- Comece pelo resultado e indique caminhos de arquivos clicáveis.
- Explique números técnicos em linguagem de usuário. Não exponha rótulos como `n=24`, códigos internos ou mensagens cruas de bibliotecas quando uma explicação útil puder ser apresentada.
