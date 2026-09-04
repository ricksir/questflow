# Validação QuestFlow Studio 3.0.7

## Objetivo

Corrigir a ordem da pesquisa web e permitir que o usuário escolha uma fonte da tabela para extrair e atualizar a questão.

## Regras validadas

1. A página carregada do Google é analisada antes de qualquer resultado orgânico.
2. Quando código ou enunciado, banca e ano são confirmados, a pesquisa termina imediatamente.
3. Uma página confirmada não provoca abertura de links adicionais apenas porque o gabarito ou a justificativa estão ausentes.
4. Os campos presentes na página confirmada são transcritos para a base.
5. A janela de resultados possui o botão **Extrair selecionado e atualizar base**.
6. A fonte selecionada é aberta em navegador visível quando ainda não foi processada.
7. Nenhuma alteração ocorre quando a fonte selecionada não confirma questão, banca e ano.

## Testes

- 37 testes automatizados concluídos com sucesso;
- teste específico de interrupção após confirmação da página do Google;
- teste de aplicação de uma fonte selecionada;
- diagnóstico integrado sem falhas;
- teste gráfico da interface concluído, incluindo escala ao vivo e criação da tela principal.

## Limitações

A pesquisa real depende do Google, do Chrome/Edge e da conexão do computador. CAPTCHA, bloqueio por login ou páginas que ocultem o conteúdo podem impedir a extração automática. Nesses casos, nenhum dado é alterado sem confirmação.
