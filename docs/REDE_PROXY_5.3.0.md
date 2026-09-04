# Rede e Proxy — QuestFlow Studio 5.3.0

## Princípio de projeto

O Chrome principal do QuestFlow comunica-se exclusivamente com a API local em `127.0.0.1` e permanece fora do proxy. Toda saída externa é centralizada em `core/network.py`.

## Modos disponíveis

- `auto`: detecta Windows/ambiente e PAC/WPAD quando disponível;
- `system`: prioriza a configuração do Windows;
- `manual`: servidor e porta informados pelo usuário;
- `pac`: URL PAC resolvida pelo WinHTTP do Windows;
- `direct`: força conexão externa sem proxy.

`localhost`, `127.0.0.1` e `::1` são adicionados ao bypass mesmo que o usuário os remova do formulário.

## Serviços integrados

A mesma camada atende Telegram, enriquecimento HTTP/Google, download da taxonomia no Google Sheets, Chrome/Selenium e o instalador/pip. Selenium Manager recebe `SE_PROXY` quando um proxy estático é resolvido.

## Credenciais

No Windows, senha de proxy manual é protegida por DPAPI no arquivo `data/proxy_credentials.dat`. A senha não é gravada em `config.json` nem devolvida pela API web. Em autenticação integrada/SSO, o Chrome/Selenium pode usar a política/credenciais do Windows; para chamadas Python que recebam HTTP 407, o diagnóstico orienta a usar credenciais Basic quando a infraestrutura exigir autenticação explícita.

## Certificados corporativos

O contexto TLS adiciona as autoridades das lojas `ROOT` e `CA` do Windows, reduzindo falhas em redes com inspeção HTTPS e CA institucional instalada na máquina.

## Primeira instalação atrás de proxy

Se o proxy não estiver definido no Windows, execute `CONFIGURAR_REDE_PROXY.bat` antes de `INSTALAR_E_DIAGNOSTICAR.bat`. O configurador usa apenas Python/Tkinter e funciona antes das dependências de terceiros.
