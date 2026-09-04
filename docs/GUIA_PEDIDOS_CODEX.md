# Como pedir alterações do QuestFlow ao Codex

Use a fonte de desenvolvimento:

```text
C:\Users\user\OneDrive\UNB\ChatGPT\Rick\QuestFlow
```

Não indique `C:\Users\user\QuestFlow` como fonte: essa é a instalação em uso.

## Correção pontual

```text
Implemente uma correção no QuestFlow.

FONTE:
C:\Users\user\OneDrive\UNB\ChatGPT\Rick\QuestFlow

PROBLEMA:
[o que acontece hoje]

COMO REPRODUZIR:
1. Abra...
2. Clique...
3. Observe...

RESULTADO ESPERADO:
[o comportamento correto e visível]

PRESERVAR:
- banco, respostas e progresso;
- pareamento e fila offline;
- funcionalidades não relacionadas.

VALIDAÇÃO:
- crie um teste de regressão;
- execute os testes relacionados;
- verifique a tela no tamanho onde ocorreu o problema.

Implemente e valide. Não pare apenas no diagnóstico.
```

## Release instalável

```text
Implemente o hotfix QuestFlow Studio <versão> e, se o Mobile mudar,
QuestFlow Mobile <versão>.

Use a fonte canônica do projeto e preserve todos os dados existentes.

ESCOPO:
[lista objetiva de mudanças]

CRITÉRIOS DE ACEITE:
- [resultado verificável 1]
- [resultado verificável 2]
- nenhuma regressão em [fluxos relacionados]

ENTREGA:
- código atualizado;
- ZIP instalável do Studio;
- APK somente se houver mudança Mobile;
- manifestos e CHANGELOG;
- SHA-256;
- relatório dos testes realmente executados;
- instruções de atualização e rollback.

Use a skill $questflow-release. Não declare conclusão sem verificar os artefatos.
```

## Mudança grande de produto

```text
Analise e implemente esta evolução do QuestFlow.

OBJETIVO DO USUÁRIO:
[decisão ou tarefa que a tela deve facilitar]

ESTADO ATUAL:
[capturas, comportamento e dados reais]

ESTADO DESEJADO:
[resultado final]

FORA DO ESCOPO:
[o que não deve mudar]

Execute em etapas independentes:
1. diagnóstico da causa e impacto;
2. plano curto com arquivos e testes;
3. implementação;
4. testes e revisão de regressão;
5. pacote, somente se solicitado.
```

## Informações que melhoram muito o resultado

- Informe sempre a versão instalada e a versão pretendida.
- Anexe a tela inteira e descreva onde clicou; a imagem é evidência, não substitui o comportamento esperado.
- Diga se deseja apenas diagnóstico, correção no código ou pacote instalável.
- Para números divergentes, informe o valor mostrado e quais registros deveriam compô-lo.
- Para layout, informe resolução, zoom e se há rolagem ou conteúdo cortado.
- Para Mobile, informe modelo do aparelho, Android, versão do app, estado da rede e se o Studio estava aberto.
- Defina como sucesso algo observável, não apenas “melhorar” ou “otimizar”.
