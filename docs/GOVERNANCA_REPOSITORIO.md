# Governança do repositório QuestFlow

## Estado atual

O repositório `ricksir/questflow` é privado. A integração contínua valida alterações em `main` e em pull requests destinados a `main`.

Os checks atuais são:

- higiene do repositório, executada antes da instalação das dependências Python;
- `Python tests`
- `Studio web and Mobile`, incluindo validação da matriz de dependências do Expo e auditoria de vulnerabilidades altas ou críticas;

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

Somente atualizações de correção (`patch`) do Mobile são agrupadas. Atualizações menores permanecem separadas para que cada incompatibilidade seja visível. React Native `0.x` exige cuidado adicional: uma troca como `0.86` para `0.87` pode conter mudanças incompatíveis, embora ferramentas semânticas a classifiquem como `minor`.

Upgrades de plataforma são deliberados e ficam fora dos PRs automáticos: Expo SDK major, React/React DOM major, React Native minor/major e TypeScript major. Eles devem ser feitos juntos em uma branch própria, seguindo a matriz oficial do Expo e executando:

```powershell
Set-Location mobile
npm ci
npx expo install --fix
npx expo install --check
npx expo-doctor
npm run typecheck
npm run test:core
npm run audit:high
```

`expo install --check` e `npm run audit:high` também rodam na CI. Um conflito de peer dependency deve ser resolvido pela matriz compatível; `--force`, `--legacy-peer-deps` e `npm audit fix --force` não são aceitos como correção.

Em 5 de setembro de 2026, a árvore do Mobile mantém a família Metro em `0.84.5`, patch que remove a dependência vulnerável `image-size` sem mudar o Expo SDK 57 ou o React Native 0.86. O `npm audit` ainda informa 13 alertas moderados transitivos em `expo-router` e no toolchain de configuração do Expo. As correções automáticas sugeridas exigem versões incompatíveis ou downgrade do Expo; por isso esses alertas permanecem monitorados até existir uma atualização compatível da matriz oficial.

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

