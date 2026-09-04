# QuestFlow Studio 4.2.0

## Atualização estrutural 4.2 — redução da dívida técnica

Esta versão reorganiza a aplicação sem alterar o formato do banco nem o fluxo principal de uso.

- `app.py` deixou de concentrar a interface inteira e passou a funcionar como **composition root**;
- cada área da interface foi separada em módulos sob `ui/`;
- revisão, enriquecimento web, análise apurada e editor de questões foram isolados;
- leituras e escritas do banco agora passam por serviços distintos (`QuestionQueryService` e `QuestionCommandService`);
- o esquema SQLite ganhou migrações versionadas e auditáveis;
- previsões do motor adaptativo passam a ser persistidas por tentativa;
- o painel calcula Brier score, log loss e erro esperado de calibração;
- testes arquiteturais impedem a volta do acesso direto ao banco dentro das views.

A migração é automática. O banco anterior continua compatível.


## Engineering Upgrade — Adaptive Mission Control

A versão 4.1 aprofunda a arquitetura do QuestFlow sem depender de complexidade ornamental. O foco é previsibilidade, explicabilidade, segurança operacional e evolução gradual.

### Agendamento de memória

- Integração opcional com o pacote oficial **Py-FSRS 6**.
- Persistência do cartão FSRS por questão, com `due`, estabilidade, dificuldade e rating.
- Fallback automático para o motor DSR local quando a extensão não estiver disponível.
- Nenhuma indisponibilidade da extensão interrompe o estudo.

### Política adaptativa por matéria e assunto

- Novo bandit contextual UCB para equilibrar exploração e reforço.
- Assuntos pouco vistos recebem bônus de cobertura.
- Assuntos com maior taxa de erro, menor retenção ou longo tempo sem revisão ganham prioridade.
- A rotação continua respeitando diversidade e status de aprovação.

### Gamificação educativa

- XP calculado por dificuldade, acerto, tempo, primeira tentativa e sequência.
- Níveis com curva progressiva e transparente.
- Sem sorteio, compras, punição por ausência, ranking público ou mecanismos compulsivos.
- O Telegram usa a recompensa real calculada pelo motor, em vez de XP fixo.

### Responsividade e execução em segundo plano

- Novo runtime assíncrono isolado, com concorrência limitada e encerramento controlado.
- Tkinter permanece exclusivamente na thread principal.
- Base para mover OCR, navegador, Telegram e manutenção para tarefas estruturadas sem criar threads ilimitadas.

### Observabilidade

- Verificação de latência e tamanho do SQLite/WAL.
- Contagem de falhas de envio, correções pendentes e fila de saída.
- Painel Mission Control mostra saúde, nível, XP, scheduler e política de assuntos.

### Qualidade

- 90 testes automatizados.
- Diagnóstico integrado, compilação completa, teste gráfico e benchmark com 5.000 questões.
- Configuração de análise estática em `pyproject.toml`.
- Documento de auditoria técnica em `docs/ENGINEERING_AUDIT_4.1.md`.

> O projeto usa práticas inspiradas em software de alta confiabilidade, mas não é certificado, validado ou afiliado à NASA.

---

## Histórico: QuestFlow Studio 4.0.0

## QuestFlow 4.0 — painel adaptativo, motor de memória e Telegram legível

A versão 4.0 reorganiza o fluxo de estudo em torno de três princípios: explicações legíveis, seleção adaptativa transparente e operação local resiliente.

### Telegram

- A explicação longa não é mais comprimida na pequena área nativa do quiz.
- Por padrão, após a resposta o bot envia um cartão separado com resultado, alternativa escolhida, alternativa correta, explicação completa e botões de ação.
- Explicações extensas são divididas automaticamente em partes legíveis.
- O quiz recebe botões **Ver explicação**, **Corrigir questão**, **Próxima** e **Meu desempenho**.
- O cartão de resultado mostra sequência, tempo de resposta, XP e retenção prevista.

### Motor adaptativo local

- Estado de memória por questão: dificuldade, estabilidade, recuperabilidade e tempo médio de resposta.
- Curva de esquecimento inspirada na família DSR/FSRS.
- Modelo logístico incremental que aprende localmente com o histórico de respostas.
- Retenção-alvo configurável entre 70% e 97%.
- Priorização combina risco de esquecimento, vencimento, novidade, cobertura, correções e status de aprovação.
- O modelo é interpretável, funciona sem nuvem e mantém compatibilidade com bancos anteriores.

### Painel Mission Control

A nova aba **Painel adaptativo** mostra retenção prevista, revisões vencidas, questões novas, acurácia histórica, quantidade de amostras do modelo e prioridade por matéria.

### Desempenho e manutenção

- SQLite configurado com WAL, `synchronous=NORMAL`, cache em memória e `mmap` para reduzir esperas.
- Novos índices para fila adaptativa e questões suspensas.
- Migração automática das novas colunas sem apagar a base existente.
- A suíte inclui testes de curva de esquecimento, atualização de memória, aprendizado incremental, prioridade e migração.

> O QuestFlow 4.0 adota práticas de engenharia e teste inspiradas em software crítico, mas não é um produto certificado pela NASA nem por qualquer agência espacial.



## Instalação silenciosa e inteligente — 3.0.15

A mensagem amarela `WARNING: Cache entry deserialization failed, entry ignored` vinha do cache local do `pip`, não do QuestFlow. Ela não significava falha na instalação.

A versão 3.0.15 atualiza o instalador para:

- não usar o cache do `pip`, eliminando o aviso de cache corrompido;
- não atualizar o `pip` em toda execução;
- instalar dependências somente quando o `requirements.txt`, o Python ou o ambiente mudarem;
- executar `pip check` e teste de importação antes de considerar a instalação válida;
- iniciar o programa sem reinstalar os pacotes a cada abertura;
- oferecer `REPARAR_INSTALACAO.bat` para uma reinstalação limpa quando necessária.

## Segurança do ciclo e prioridade de aprovação

### Questões encaminhadas para correção

Quando o botão **⚠️ Corrigir esta questão** é usado no Telegram, a questão fica temporariamente suspensa e não volta ao ciclo antes da correção. Ao usar **Salvar e aprovar** — ou marcar a solicitação como resolvida — o QuestFlow:

1. retira a suspensão;
2. torna a questão elegível novamente;
3. marca a revisão como vencida para o ciclo;
4. dá prioridade à questão quando a matéria correspondente entrar na rotação;
5. remove essa prioridade especial depois do próximo envio bem-sucedido.

### Proteção contra envio em massa ao iniciar

A versão anterior executava a manutenção de questões sem resposta e falhas antigas antes de verificar se o ciclo diário estava ativado. Um estoque histórico de entregas podia, portanto, ser processado após a inicialização. Isso explica o envio inesperado de muitas questões.

A versão 3.0.14 adiciona:

- quarentena automática do estoque antigo na primeira abertura da versão;
- espera padrão de 5 minutos após iniciar o aplicativo;
- deduplicação por questão, considerando apenas a entrega mais recente;
- somente 1 reenvio sem resposta por verificação;
- limite padrão de 3 reenvios sem resposta por dia e por sessão;
- limite de 1 falha automática por lote e 5 por sessão;
- ciclo perdido também respeita a espera de segurança da inicialização.

Esses limites podem ser ajustados em **Fluxo Telegram**.

### Reiniciar ciclo de estudos

O botão **Reiniciar ciclo de estudos** apaga somente o progresso de estudo: histórico de envios, respostas, acertos, erros, ciclos e repetição espaçada. A base de questões e a fila **Correções Telegram** são preservadas. Para confirmar, é necessário digitar `REINICIAR`.

### Ordem dos status

Com a opção de questões aprovadas ativada, a seleção segue esta ordem:

1. `APROVADO`;
2. `APROVADO_AUTOMATICAMENTE`, somente para completar o ciclo quando não houver aprovadas suficientes;
3. questões pendentes não são enviadas.

## Correções da versão 3.0.8

### Página carregada do Google como fonte prioritária

A pesquisa agora segue uma regra direta:

1. abre a página do Google;
2. confirma código ou enunciado, banca e ano;
3. se a correspondência for exata, transcreve imediatamente os campos exibidos na própria página;
4. atualiza o banco;
5. não abre resultados adicionais nem inicia outra pesquisa.

Links adicionais somente são abertos quando a página carregada do Google não confirma a questão. A falta de gabarito ou justificativa, isoladamente, não faz o programa abandonar uma página já confirmada.

### Extração manual da fonte selecionada

Na janela **Pesquisa web da questão**, foi incluído o botão **Extrair selecionado e atualizar base**. Selecione a linha da página carregada do Google ou de outro resultado e clique no botão. O programa abre a fonte quando necessário, confirma questão, banca e ano e preenche apenas os campos ausentes ou incompletos, como enunciado, alternativas, gabarito e justificativa.


Aplicativo local para Windows que reúne importação de PDFs/imagens, banco organizado de questões, revisão, estudo adaptativo e envio cíclico pelo Telegram.


## Expansão automática da resposta do Google

Antes de interpretar a página de pesquisa, o QuestFlow agora procura e aciona controles como **Mostrar mais**, **Ver mais**, **Mostrar tudo** e **Mais detalhes**. O programa aguarda a resposta crescer e o DOM estabilizar antes de ler os campos.

Isso permite capturar informações que estavam recolhidas na Visão Geral do Google, especialmente:

- informações gerais da questão;
- banca e ano;
- órgão, cargo, matéria e assunto;
- enunciado;
- gabarito;
- justificativa ou explicação.

A janela de resultados informa se o botão foi acionado e quantos cliques foram necessários. O mesmo procedimento também é usado quando a página carregada do Google é escolhida manualmente em **Extrair selecionado e atualizar base**.


## Correções e melhorias da versão 3.0.6

### Pesquisa exclusivamente pelo Google em navegador visível

A pesquisa web passou a abrir o **Google em uma janela real do Chrome ou Edge** e ler o conteúdo depois que a página terminar de carregar. O programa não usa Bing, DuckDuckGo ou RSS como mecanismo de pesquisa nesta versão.

A consulta segue exatamente esta ordem:

1. se houver código, pesquisa `"Q1234567" quais as informações, o enunciado da questão, gabarito e a justificativa da questão?`;
2. lê a própria página de resultados do Google, inclusive os blocos visíveis de informações da questão;
3. confirma código, banca e ano;
4. extrai enunciado, gabarito, justificativa, órgão, cargo, área, especialidade e turno quando esses dados aparecerem;
5. somente quando a própria página do Google não trouxer todos os dados necessários, abre até cinco resultados orgânicos, um de cada vez;
6. se a etapa do código falhar, repete o processo usando apenas o enunciado e a mesma pergunta orientadora.

A janela de resultados informa separadamente se:

- a página do Google foi realmente lida;
- o código foi confirmado;
- banca e ano coincidiram;
- um resultado adicional precisou ser aberto;
- o gabarito e a justificativa foram encontrados;
- os campos foram transcritos para a base.

A pesquisa utiliza um perfil próprio em `data/google_browser_profile`, permitindo que consentimento e sessão sejam preservados entre buscas. Se o Google apresentar CAPTCHA ou verificação de tráfego, o programa informa a ocorrência e não preenche dados sem confirmação.


## Correções e melhorias da versão 3.0.4

### Pesquisa web em duas etapas, sem misturar os termos

A pesquisa da questão foi alterada para seguir exatamente esta ordem:

1. pesquisa **somente o código**, por exemplo `"Q2096370"`;
2. abre os resultados e lê a página encontrada;
3. confirma se o enunciado, a banca e o ano são os mesmos da questão do banco;
4. procura o gabarito dentro da página aberta;
5. se o código não localizar uma correspondência confirmada — ou se a página correta não trouxer o gabarito — executa uma segunda pesquisa usando **somente o enunciado**.

O código nunca é concatenado com o enunciado, banca, ano ou órgão na mesma consulta. Banca e ano são usados apenas depois, durante a validação da página.

Um resultado de busca ou trecho exibido pelo Google/Bing/DuckDuckGo não é suficiente para preencher o banco. O QuestFlow precisa conseguir abrir a página e confirmar:

- correspondência do enunciado;
- banca;
- ano;
- presença do gabarito na própria página, quando o campo estiver faltando.

Na janela de resultados, o programa mostra separadamente:

- etapa utilizada: código ou enunciado;
- código exato;
- banca confirmada;
- ano confirmado;
- página aberta pelo programa;
- gabarito lido no site;
- fonte confirmada.

O botão **Abrir fonte confirmada / gabarito** abre diretamente a página usada para validar e preencher a questão.


## Correções e melhorias da versão 3.0.3

### Pesquisa web confirmada pelo código e pelo enunciado

A pesquisa assistida foi refeita para evitar resultados errados ou vazios:

- consulta simultaneamente **Google, Bing, DuckDuckGo e DuckDuckGo Lite**;
- pesquisa o código isolado, o código com gabarito, trechos exatos do enunciado e consultas restritas a sites de questões;
- executa os mecanismos em paralelo para não deixar a interface parada quando um provedor está lento;
- abre os resultados encontrados e também tenta ler a página da questão;
- compara o código e a semelhança do enunciado antes de considerar que é a mesma questão;
- rejeita páginas que reutilizam o mesmo número para uma questão de outro site ou de outro concurso;
- recupera, quando disponíveis, ano, banca, órgão, prova, enunciado completo, alternativas, tipo e gabarito;
- preenche apenas campos ausentes ou claramente incompletos;
- registra as fontes e os campos transcritos em `enriquecimento_web`;
- mostra na janela de resultados se houve correspondência confirmada, código exato, gabarito localizado e quais campos foram aplicados.

A pesquisa de várias pendentes continua disponível. Selecione linhas com `Ctrl` ou `Shift` e use **Web: várias pendentes**.

### Questão anulada

Na aba **Revisar banco** foram adicionados os botões **Questão anulada** e **Marcar anulada**.

Ao confirmar:

- a questão é retirada da base ativa;
- não participa do ciclo de estudos;
- não é enviada ao Telegram;
- seus registros de estudo e envio são removidos por integridade referencial;
- uma cópia de auditoria fica na tabela local `excluded_questions`;
- o mesmo código/fingerprint não volta silenciosamente em uma nova importação.

A opção **Excluir da base** continua disponível para exclusão definitiva comum.



## Correções e melhorias da versão 3.0.2

### Textos e escala da interface

- os campos de Configurações deixaram de usar caixas de altura fixa, evitando textos de ajuda cortados;
- os botões `A−` e `A+` agora alteram imediatamente as fontes de Labels, Textos, tabelas, botões e campos;
- a escala não é acumulada de forma incorreta: cada tamanho é recalculado a partir da fonte-base;
- o tamanho selecionado também é sincronizado com **Configurações → Escala da interface**;
- as ações da revisão foram distribuídas em duas linhas para não desaparecerem em janelas menores;
- o texto de andamento da releitura, OCR e pesquisa passa a quebrar linha quando necessário.

### Pesquisa de uma ou várias questões pendentes

A aba **Revisar banco** possui agora:

- **Web: questão selecionada**;
- **Web: várias pendentes**;
- seleção múltipla com `Ctrl` ou `Shift` na tabela;
- escolha da quantidade de pendentes a pesquisar quando nenhuma seleção múltipla for usada;
- relatório final por código, quantidade de resultados, confiança e eventual erro;
- possibilidade de abrir a consulta no navegador mesmo quando o programa não conseguir extrair resultados automaticamente.

A busca utiliza consultas alternativas e tenta, em sequência, os formatos HTML do DuckDuckGo, DuckDuckGo Lite e Bing. A alteração de HTML ou a indisponibilidade de um provedor não impede a tentativa nos demais.

### Análise apurada que realmente relê o PDF

O processamento de pendentes agora:

1. procura o caminho antigo salvo no banco;
2. tenta localizar o PDF pelo nome em pastas adicionadas pelo usuário, Downloads e Documentos;
3. permite selecionar a pasta raiz dos PDFs antes do processamento;
4. relê todas as questões escolhidas, mesmo quando o reparo local pareça suficiente;
5. recria o Markdown, força OCR e análise de imagens em DPI configurável, padrão 300;
6. compara a questão por código, número e semelhança do enunciado;
7. informa separadamente PDFs não localizados, falhas de releitura e questões não encontradas dentro do documento.

Use **Analisar selecionadas** para uma ou várias linhas, ou **Analisar todas pendentes** para o banco inteiro.


## Principais mudanças da versão 3.0

### Telegram resiliente

- cada questão recebe até **3 tentativas imediatas** por padrão;
- falhas temporárias usam espera progressiva (*backoff*) e respeitam o tempo indicado pelo Telegram;
- o motivo da falha, categoria, quantidade de tentativas e próxima tentativa ficam salvos no histórico;
- falhas temporárias podem ser reenviadas automaticamente no intervalo configurado;
- botões **Ver motivo**, **Reenviar selecionada** e **Reenviar todas com erro**;
- envio avulso pela tela de prévia também registra a falha e tenta novamente;
- erros permanentes, como token inválido, bot bloqueado, Chat ID incorreto ou conteúdo inválido, não entram em repetição infinita.

### Extração Markdown → estrutura da questão

O fluxo de leitura passou a preparar primeiro um pacote Markdown por documento:

1. gera Markdown paginado e extrai imagens com `PyMuPDF4LLM`;
2. armazena o resultado em cache por hash do arquivo;
3. aplica leitura textual, análise visual ou OCR conforme o tipo do documento;
4. identifica questão, alternativas, gabarito, metadados e imagem;
5. classifica matéria, aula e assunto pela taxonomia AFRFB;
6. envia somente registros estruturalmente válidos para aprovação automática.

Para questões pendentes, o modo apurado pode usar um OCR Tesseract completo em DPI maior. O cache fica em `data/markdown_cache`.

### Pesquisa web assistida

A pesquisa é opcional e vem desativada. Quando habilitada:

- pesquisa pelo código, parte exata do enunciado, banca, ano e órgão;
- apresenta os resultados e a confiança;
- preenche automaticamente apenas campos vazios quando há correspondência muito forte;
- nunca aprova uma questão apenas porque um resultado da internet foi encontrado;
- mantém a origem e os dados da pesquisa no registro para revisão.

Use a função somente para conferir metadados e gabaritos publicados legitimamente. A disponibilidade depende da internet e dos sites encontrados.

### Estudo adaptativo aprimorado

A estratégia `auditor_inteligente` combina:

- rotação entre matérias e assuntos;
- revisão vencida e tempo desde o último contato;
- probabilidade bayesiana de erro, que evita distorções por amostras pequenas;
- questões novas e pouco enviadas;
- intervalo adaptativo inspirado em repetição espaçada, ajustado pelo histórico e pela facilidade da questão.

### Interface customizável

Em **Configurações → Aparência**:

- temas claro, escuro e alto contraste;
- cores de destaque laranja, azul, verde, roxo ou vermelho;
- escala da interface;
- densidade compacta, confortável ou ampla;
- largura e recolhimento da barra lateral.

Também estão disponíveis:

- botões `A−` e `A+` no cabeçalho;
- barra lateral recolhível;
- painéis de revisão e fluxo redimensionáveis;
- modos só lista, só editor, horizontal/vertical e troca de lados;
- tamanho e posição da janela preservados;
- tabelas ordenáveis e colunas redimensionáveis.

## Instalação

1. Extraia o ZIP inteiro para uma pasta normal do Windows.
2. Instale Python 3.11 ou superior, marcando **Add Python to PATH**.
3. Instale Tesseract OCR com o idioma Português.
4. Execute `INSTALAR_E_DIAGNOSTICAR.bat`.
5. Execute `INICIAR_QUESTFLOW_STUDIO.bat`.

O ambiente Python fica na pasta `.venv` do programa.

## Preservar os dados de uma versão anterior

Com as duas versões fechadas, copie para `data` da versão 3.0:

- `questflow_questions.sqlite`;
- `config.json`;
- pasta `question_images`;
- opcionalmente `markdown_cache`, para não gerar novamente os documentos já processados.

O banco recebe as novas colunas automaticamente na primeira abertura.

## Reenviar questões com erro

Na aba **Fluxo Telegram**:

1. localize a linha vermelha no histórico;
2. selecione-a;
3. clique em **Ver motivo** para saber exatamente o que ocorreu;
4. clique em **Reenviar selecionada**.

Para todas as falhas, use **Reenviar todas com erro**. Marque **Reenviar automaticamente falhas temporárias** para que o motor faça novas tentativas sem intervenção.

## Importar bancos já existentes

Na aba **Backup e exportação**:

- **Importar banco salvo (JSON/QFLOW/QFLOWPKG)**;
- **Migrar banco do PDF Importer (.SQLITE)**;
- exportação JSON, CSV, banco QuestFlow e backup SQLite.

## Testes

- `TESTAR_COMPONENTES.bat`: diagnóstico rápido do ambiente;
- `TESTAR_SUITE_COMPLETA.bat`: suíte automatizada;
- `python run_tests.py`: execução direta da suíte.

A matriz está em `tests/TEST_MATRIX.md` e o relatório desta versão em `docs/VALIDACAO_3.0.13.md`.

## Limites importantes

- o envio automático depende de o computador estar ligado, o programa aberto e a internet disponível;
- a conexão real com o Telegram não pode ser validada sem o token e o Chat ID do usuário;
- resultados encontrados na internet devem ser revisados, pois páginas podem estar indisponíveis, desatualizadas ou incorretas;
- o programa não contorna páginas privadas, autenticação, paywalls ou bloqueios dos sites.


## Correção da versão 3.0.1

A conversão por PyMuPDF4LLM agora ocorre em um **processo isolado**. No Windows, versões 0.3.x da biblioteca podem manter o PDF temporário aberto por alguns instantes após a conversão; isso provocava `WinError 32` ao diagnóstico tentar apagar a pasta temporária.

Com o processo isolado:

- o processo auxiliar abre e converte o PDF;
- o Markdown e as imagens são devolvidos ao QuestFlow;
- o processo auxiliar é encerrado;
- todos os identificadores nativos do PDF são liberados antes da limpeza;
- o arquivo original pode ser removido, movido ou substituído imediatamente após a conversão.

O diagnóstico e a suíte completa passaram sem falhas, incluindo um teste específico de liberação imediata do arquivo PDF.


## Correções e melhorias da versão 3.0.5

- A pesquisa por código passa a usar `"Q1234567" qual o texto da questão, gabarito e justificativa?`.
- Se a etapa do código não confirmar a questão ou não localizar dados faltantes, o programa pesquisa o enunciado com a mesma pergunta orientadora.
- Cada etapa abre sequencialmente pelo menos cinco links, quando disponíveis, e continua até dez caso ainda não haja confirmação.
- Banca, ano e enunciado precisam coincidir antes de qualquer transcrição.
- O Bing RSS foi incluído como mecanismo alternativo quando os buscadores HTML bloqueiam a leitura automática.
- O programa procura gabaritos também em atributos e dados estruturados ocultos na página.
- Justificativas, comentários, resoluções e gabaritos comentados podem ser transcritos para o campo de explicação quando a página for confirmada.
- A janela de resultados informa quantas páginas foram abertas e se o gabarito e a justificativa foram confirmados.


## Verificação “Não sou um robô” — versão 3.0.9

Se o Google apresentar CAPTCHA ou seleção de imagens, o QuestFlow mantém o Chrome/Edge aberto por até **15 minutos**. Conclua o desafio normalmente. Assim que o Google voltar à página de resultados, o programa continua a leitura automaticamente.

O QuestFlow não tenta contornar o CAPTCHA. Se a janela for fechada ou a verificação não for concluída no prazo, nenhum dado da questão é alterado e a pesquisa informa o motivo. O perfil em `data/google_browser_profile` preserva a sessão para reduzir novas verificações.


## Google Modo IA e confirmação antes de atualizar — versão 3.0.10

A pesquisa assistida agora trabalha **somente no Modo IA do Google**:

1. abre `google.com/ai` usando o perfil local do QuestFlow;
2. pesquisa primeiro pelo código da questão e, se necessário, pelo enunciado;
3. não abre links de resultados;
4. aguarda a resposta terminar de carregar e clica em **Mostrar mais** quando existir;
5. percorre o texto renderizado e confirma código ou enunciado, banca e ano;
6. extrai enunciado, alternativas, gabarito, justificativa e metadados disponíveis.

A pesquisa **não altera mais a base automaticamente**. Na janela do resultado, use
**Preparar prévia e atualizar base**. O QuestFlow abrirá a prévia visual do Telegram
com os dados propostos:

- **OK — atualizar base:** grava os dados e atualiza imediatamente o editor à direita;
- **Cancelar:** fecha a prévia sem alterar a questão, permitindo fazer outra busca.

A verificação humana do Google continua sendo aguardada por até 15 minutos. O programa
não tenta resolver nem contornar CAPTCHA.


## Otimização do Google Modo IA — versão 3.0.11

A integração com o Google foi refeita para reduzir o tempo de abertura e melhorar a captura do texto que já aparece na tela:

- o Chrome ou Edge permanece em uma sessão reutilizável entre pesquisas;
- o carregamento usa estratégia `eager`, permitindo acessar o DOM antes de imagens e recursos secundários terminarem;
- o programa procura o bloco semântico que contém código, banca, ano, enunciado, alternativas, gabarito e justificativa, em vez de ler indiscriminadamente toda a página;
- a espera termina antecipadamente quando a resposta está completa e estável;
- a página é rolada automaticamente para carregar trechos sob demanda;
- títulos com ícones ou Markdown e alternativas no formato `Alternativa A:` são reconhecidos;
- a janela de resultados informa tempo total, método de captura e quantidade de caracteres lidos;
- o botão **Fechar sessão Google** permite reiniciar o navegador caso a sessão fique inconsistente.

A primeira consulta ainda precisa iniciar o navegador. As consultas seguintes normalmente reutilizam a mesma sessão e o perfil localizado em `data/google_browser_profile`.


## Encaminhar uma questão do Telegram para correção — versão 3.0.12

Cada enquete enviada pelo QuestFlow possui o botão:

```text
⚠️ Corrigir esta questão
```

Ao tocar nele, a questão entra na aba **Correções Telegram** do programa. A fila mostra:

- data da solicitação;
- código e matéria;
- usuário que solicitou a correção;
- status `pendente`, `aberta` ou `resolvida`;
- prévia do enunciado.

Use **Abrir e editar** para ir diretamente à aba **Revisar banco**, com a questão selecionada. Depois de corrigir, use **Salvar e aprovar** para atualizar a base e concluir automaticamente as solicitações ligadas àquela questão. Também é possível marcar uma solicitação como resolvida ou removê-la apenas da fila.

O capturador de botões inicia sempre que o token e o Chat ID estiverem configurados, mesmo que o ciclo diário esteja pausado. Quando o computador volta a funcionar, o QuestFlow busca as atualizações ainda disponíveis no Telegram e mantém uma fila local de processamento e confirmação. Se a solicitação já não estiver disponível no Telegram, o botão continua visível na mensagem e pode ser acionado novamente.


## Continuidade de estudo e mapa de aulas — versão 3.0.13

### Reenvio de questões sem resposta

Na aba **Fluxo Telegram**, ative **Reenviar questões que ficaram sem resposta** e configure:

- tempo de espera em horas;
- quantidade máxima de reenvios.

O QuestFlow identifica quizzes enviados que ainda não possuem resposta e os envia novamente depois do prazo. Cada reenvio fica ligado ao envio anterior, evitando duplicidade infinita. Quando o programa estava fechado no horário previsto, a verificação é executada assim que ele volta a funcionar.

### Correções solicitadas com o computador desligado

Os cliques no botão **⚠️ Corrigir esta questão** passam por uma caixa de entrada persistente:

1. o QuestFlow busca as atualizações pendentes quando inicia;
2. grava o clique no SQLite antes de processá-lo;
3. cria ou reativa a solicitação na aba **Correções Telegram**;
4. mantém a confirmação em uma caixa de saída local caso a internet falhe;
5. tenta enviar a confirmação novamente automaticamente.

O identificador da última atualização processada também é salvo, reduzindo o risco de perder ou duplicar solicitações após uma interrupção.

### Nova aba Mapa de aulas

A aba **Mapa de aulas** cruza a taxonomia da planilha com o banco e o histórico do Telegram. Para cada matéria e aula, mostra:

- assuntos previstos na planilha;
- quantidade de questões no banco;
- aprovadas e pendentes;
- quantas questões diferentes já foram enviadas;
- total de envios;
- quantas já receberam resposta;
- data do último envio;
- situação: **Sem questões**, **Com questões, nunca enviadas**, **Envio parcial** ou **Todas já enviadas**.

A tela possui filtros por matéria, texto e situação, além de atualização pela planilha Google, importação de XLSX e exportação do mapa em CSV.


## Migração para 4.0

Consulte `docs/MIGRACAO_4.0.md`. Em resumo, copie apenas o banco e as pastas de dados; não copie o ambiente `.venv`. As novas estruturas são criadas automaticamente.
