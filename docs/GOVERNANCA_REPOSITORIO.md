# Governança do repositório QuestFlow

## Estado atual

O repositório `ricksir/questflow` é privado. A integração contínua valida alterações em `main` e em pull requests destinados a `main`.

Os checks atuais são:

- higiene do repositório, executada antes da instalação das dependências Python;
- `Python tests`
- `Studio web and Mobile`

O gate de higiene recusa dados persistentes, credenciais, artefatos instaláveis, diretórios gerados, links simbólicos e arquivos versionados acima de 10 MiB. Ele também confere as versões canônicas e o checksum do lock Python.

No plano atual do GitHub, regras de proteção não são aplicadas a este repositório privado. Portanto, a aprovação da CI é uma política operacional do projeto, mas ainda não é uma trava do servidor. Não interprete a ausência de bloqueio do botão de merge como aprovação técnica.

## Fluxo obrigatório do projeto

1. Crie uma issue para descrever o problema ou a melhoria.
2. Crie uma branch curta a partir de `main`.
3. Implemente e execute as validações locais aplicáveis.
4. Abra um pull request para `main`.
5. Aguarde os dois checks da CI terminarem com sucesso.
6. Revise o diff, os riscos e as evidências antes de incorporar.
7. Não use force-push nem exclua `main`.

## Dependências

O Dependabot verifica semanalmente:

- dependências npm do Mobile;
- versões das ações usadas pela CI.

Atualizações menores e de correção do Mobile são agrupadas para reduzir ruído. Atualizações maiores permanecem separadas e exigem validação explícita.

As dependências Python não são atualizadas automaticamente: o projeto mantém `requirements.txt`, `requirements.lock` e `requirements-dev.lock`, e a atualização precisa preservar o lock e seu checksum entre plataformas.

## Proteção futura da `main`

Quando a conta oferecer proteção para repositório privado, configurar uma regra ativa para a branch padrão com:

- pull request obrigatório;
- os checks `Python tests` e `Studio web and Mobile` obrigatórios;
- conversas resolvidas antes do merge;
- histórico linear;
- proibição de force-push e exclusão;
- aplicação também ao administrador, sem bypass rotineiro.

Depois de ativar a regra, testar com um pull request pequeno e confirmar que um check em falha realmente bloqueia o merge.

