# Validação — QuestFlow Studio 4.1.0

## Resultado

- 90 testes automatizados: aprovados;
- compilação de todos os módulos: aprovada;
- diagnóstico integrado: aprovado;
- teste gráfico com escala ao vivo e páginas principais: aprovado;
- benchmark sintético com 5.000 questões: aprovado;
- importação de banco, Telegram, OCR, Markdown e pesquisa Google: regressão aprovada.

## Novos testes

- fallback seguro quando Py-FSRS não está instalado;
- uso da API pública do scheduler por módulo simulado;
- prioridade de assunto fraco versus dominado;
- exploração de assunto nunca visto;
- ranking reprodutível;
- curva de nível monotônica;
- XP idempotente;
- atualização de estado por assunto;
- runtime assíncrono para coroutine e função bloqueante;
- coleta de saúde do banco.

## Benchmark local

- importação de 5.000 questões: aproximadamente 0,27 s;
- seleção adaptativa de 20 questões: aproximadamente 0,10 s;
- painel agregado: aproximadamente 0,01 s.

Os tempos dependem do hardware, disco, antivírus, tamanho do banco e estado do cache.

## Limitações da validação

- a conexão real com o Telegram exige token e Chat ID do usuário;
- Py-FSRS não estava disponível no índice local do ambiente de construção, então a integração foi testada por contrato com um módulo simulado e o fallback foi testado diretamente;
- o Google Modo IA depende da conta, região, CAPTCHA e mudanças de interface.
