# Auditoria de controles do Roadmap — QuestFlow 6.8.3 Hotfix 1

## Resultado

A auditoria cruzou Roadmap/CHANGELOG, HTML, handlers JavaScript e métodos permitidos na API HTTP local.

| Evolução | Controle/ação | Situação encontrada | Correção/estado |
|---|---|---|---|
| 6.6.8 | Watchdog: verificar/atualizar/salvar | Visível em Configurações e ligado ao backend | OK |
| 6.6.8 | Reiniciar serviço | Condicional a serviço `recoverable` | Mantido condicional por segurança |
| 6.7.0 | Tutor IA / scaffolding | Navegação e ações presentes | OK |
| 6.7.1 | Entender/coletar evidência | Surge apenas com conceito de evidência insuficiente | OK; plano permanece condicional |
| 6.7.1 | Iniciar prática diagnóstica | Desaparecia quando indisponível | Agora permanece visível e desabilitado com motivo |
| 6.7.2 | Pesquisar resposta no Google com IA | Visível no editor e ligado ao backend | OK; hotfixes de captura preservados |
| 6.7.3 | Hardening/build | Utilitários BAT/CLI, não botão da UI principal | Comportamento esperado |
| 6.8.0 | Evidências híbridas | Ficava na parte profunda de Inteligência e curadoria | Atalho movido para barra superior; habilita após selecionar questão |
| 6.8.1 | Benchmark RAG 3.0 | Ficava na parte profunda do editor | Agora sempre visível no topo de Revisar Banco |
| 6.8.2 | Calibrar retrieval | Ficava na parte profunda do editor | Agora sempre visível no topo de Revisar Banco |
| 6.8.2 | Aplicar perfil recomendado | Desaparecia quando não havia recomendação | Agora permanece visível e desabilitado com explicação |
| 6.8.3 | Observabilidade retrieval | Ficava na parte profunda do editor | Agora sempre visível e destacada no topo de Revisar Banco |
| 6.8.3 | Adicionar ao Ouro | Só existe quando há candidatos reais | Mantido condicional; painel informa quando não há candidatos |

## Verificações automáticas

- 96 botões estáticos com `id` no HTML.
- 0 botões estáticos sem referência correspondente no JavaScript.
- 0 IDs HTML duplicados após a reorganização.
- Handlers confirmados para Benchmark RAG, Calibração, Observabilidade, Contexto/RAG, Grafo, Evidências híbridas e Pesquisa Google.
- Métodos de backend/API confirmados para Watchdog, evidência, Google, benchmark, calibração, rollback, baseline e observabilidade.
- 79 testes focados aprovados em duas baterias (44 controles/RAG/evidência/watchdog/tutor + 35 pesquisa Google).

## Princípio de UX adotado

Ações centrais do Roadmap não devem desaparecer quando temporariamente indisponíveis. Quando a indisponibilidade é contextual, o controle deve permanecer visível e desabilitado, com explicação em `title`/texto contextual. Exceções de segurança permanecem condicionais quando exibir a ação seria enganoso, como reinício de serviços não recuperáveis.
