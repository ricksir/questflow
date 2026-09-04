# Validação QuestFlow Studio 3.0.9

## Problema corrigido
O Google podia apresentar a verificação “Não sou um robô” e um desafio de imagens. A versão anterior encerrava o navegador ao fim do tempo normal de carregamento, sem dar tempo para a conclusão manual.

## Comportamento novo
- detecção por texto, URL `/sorry/`, formulário CAPTCHA e iframe reCAPTCHA;
- navegador visível mantido aberto por até 15 minutos;
- nenhuma automação ou contorno do desafio: a resolução é exclusivamente manual;
- continuação automática da pesquisa quando o Google redireciona aos resultados;
- interrupção segura quando o usuário fecha o navegador ou o prazo termina;
- registro do tempo aguardado e do resultado da verificação na janela de pesquisa;
- mesma proteção na leitura manual de uma fonte selecionada.

## Testes
Foram adicionados testes para: CAPTCHA resolvido pelo usuário, permanência até o limite, metadados de resolução e regressão da pesquisa Google.
