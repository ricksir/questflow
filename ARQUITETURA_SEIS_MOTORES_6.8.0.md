# Arquitetura dos seis motores — QuestFlow 6.8.0

A versão **6.8.0** mantém exatamente seis motores. Multimodal RAG 3.0 é uma evolução interna do Knowledge Engine e a extração Google precisa é uma evolução do AI Engine + Evaluation & Governance; nenhum sétimo motor foi criado.

1. **Banco Editorial** — questões, proveniência, Curadoria e persistência editorial.
2. **Learner Model** — FSRS, Knowledge Tracing, IRT, incerteza e calibração.
3. **Learning Engine** — recomendação, simulados, coleta de evidência e benchmark pedagógico.
4. **Knowledge Engine 3.0** — RAG textual, evidência visual, roteamento híbrido e grounding multimodal auditável.
5. **AI Engine** — Tutor, scaffolding, geração assistida, provedores e pesquisa Google editorial com extração focada.
6. **Evaluation & Governance Engine** — auditoria, avaliação por afirmação/evidência, diagnóstico de confiança e revisão humana.

## Fluxo de pesquisa Google 6.8.0

Editor → política de privacidade → código da questão → validação de correspondência → extração focada da justificativa → fallback por enunciado quando necessário → limiar de confiança → Evaluation & Governance → rascunho em “Explicação após a resposta” → revisão humana.

O bloco integral do Google não é mais aceito como explicação. Se não houver justificativa verificável, o sistema se abstém de preencher o campo.

## Fluxo Multimodal RAG 3.0

Questão/material → `text`, `visual` ou `hybrid` → evidências normalizadas → grounding por fonte/hash → Knowledge Engine → AI Engine/Evaluation & Governance.

Binários de imagem/PDF ficam locais por padrão. O envio externo só é preparado se o usuário habilitar explicitamente o opt-in de mídia binária no modo Personalizado do Centro de Privacidade.
