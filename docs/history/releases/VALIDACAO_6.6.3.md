# Validação técnica — QuestFlow Studio 6.6.3

## Objetivo
Corrigir a defasagem entre as edições reais do banco e os indicadores da **Curadoria inteligente**, sem reintroduzir ruído no Cloud Sync.

## Causas confirmadas
1. O botão antigo **Atualizar curadoria** apenas relia colunas agregadas; não recalculava os sinais derivados de todas as questões.
2. O critério **Fonte rastreável** considerava `fonte.arquivo`, mas ignorava a **Fonte primária / referência** que o próprio editor disponibilizava ao usuário.
3. Uma explicação podia ser salva mantendo `origem_comentario = sem_comentario`, deixando o contador de comentários congelado.
4. A dificuldade empírica era materializada principalmente quando a inteligência individual da questão era aberta, permitindo defasagem no resumo global.
5. Consultas derivadas de inteligência ainda podiam reescrever `data_json`, confundindo leitura com edição.

## Correções
- Recalculo global idempotente de origem, qualidade, status de curadoria, origem do comentário, direitos e dificuldade empírica.
- Fonte primária, URL ou documento passam a satisfazer o requisito de rastreabilidade.
- Explicação não vazia normaliza automaticamente a origem para comentário manual quando o campo ainda estiver em `sem_comentario`.
- Nova fila de atenção mostra as questões reais por indicador e o checklist ausente de cada uma.
- Salvar/aprovar uma questão atualiza o resumo da Curadoria imediatamente.
- Abertura da inteligência da questão não persiste mais snapshots derivados dentro do conteúdo editorial.
- Colunas derivadas da tabela `questions` foram declaradas transitórias no Cloud Sync.

## Testes
A suíte contém **345 testes automatizados**.

Execução final particionada:
- Grupo 1: 106/106
- Grupo 2: 120/120
- Grupo 3: 119/119
- Total: **345/345 aprovados**

Também foram executados testes específicos da 6.6.3 para:
- fonte primária contabilizada como rastreável;
- explicação salva deixando `sem_comentario`;
- reconstrução de status/qualidade/dificuldade desatualizados;
- ausência de eventos de Cloud Sync durante recalculo derivado;
- fila de atenção com motivos exatos.

## Banco de dados
Não há nova migração de schema:
- question_bank: v8
- study: v10
- ai_governance: v4

## Resultado
A Curadoria passa a refletir os dados atuais do banco. Quando um número não cair, a fila de atenção explica **qual requisito ainda falta**. O indicador de dificuldade é explicitamente tratado como dado de aprendizagem, não como campo editorial manual.
