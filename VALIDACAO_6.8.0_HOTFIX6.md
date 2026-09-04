# Validação técnica — QuestFlow Studio 6.8.0 Hotfix 6

## Escopo

Correção do retorno da pesquisa Google Modo IA e compactação avançada do editor.

## Pesquisa Google

- tempo efetivo da consulta principal elevado de 24 s para 75 s;
- recaptura efetiva elevada de 18 s para 60 s;
- espera pós-expansão de no mínimo 30 s;
- janela real de estabilidade antes da captura final;
- recaptura final após 2,2 s;
- varredura sempre inclui blocos compactos com `Gabarito` + `Explicação/Justificativa/Resolução`;
- o menor bloco útil concorre com os contêineres grandes do Google;
- o texto geral da página continua proibido como explicação.

## Interface

- cabeçalho da questão ultracompacto;
- botão para recolher/expandir os detalhes da questão;
- preferência persistida no navegador;
- pesquisa assistida e ações de revisão compactadas;
- área de explicação ampliada.

## Resultado

- 427 / 427 testes automatizados aprovados em quatro partições: 121 + 95 + 112 + 99;
- 31 testes focados no fluxo Google aprovados;
- 4 testes novos do Hotfix 6 aprovados;
- 164 arquivos Python compilados;
- `web/app.js` aprovado pelo `node --check`;
- smoke test aprovado;
- banco distribuído: `quick_check = ok` e 0 violações de chave estrangeira;
- lock de dependências SHA-256 validado.

## Banco

Nenhuma migração nova:

- question_bank v8
- study v11
- ai_governance v4
