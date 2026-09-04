# Implantação do QuestFlow Mobile Cloud Gateway 0.3

O Gateway é a ponte sempre disponível entre o celular e o Studio. Ele **não substitui o Studio** e **não é o banco principal**.

## Pré-requisitos de produção

- servidor/VPS com Python 3.11+ e armazenamento persistente;
- nome DNS/subdomínio acessível pelo celular;
- HTTPS válido na frente do processo (reverse proxy ou serviço equivalente);
- porta interna do Gateway não precisa ficar exposta diretamente à Internet;
- chave administrativa aleatória com pelo menos 20 caracteres.

## Arquivo necessário no servidor

Copie `mobile_cloud_gateway.py` para o servidor. O Gateway usa somente a biblioteca padrão do Python.

## Inicialização

Linux/macOS:

```bash
export QUESTFLOW_BRIDGE_KEY='gere-uma-chave-longa-e-aleatoria'
python3 mobile_cloud_gateway.py --host 127.0.0.1 --port 8787 --db /var/lib/questflow/mobile-cloud-gateway.sqlite
```

Windows Server (PowerShell):

```powershell
$env:QUESTFLOW_BRIDGE_KEY='gere-uma-chave-longa-e-aleatoria'
python mobile_cloud_gateway.py --host 127.0.0.1 --port 8787 --db C:\QuestFlowGateway\mobile-cloud-gateway.sqlite
```

Em produção, publique `127.0.0.1:8787` por um reverse proxy HTTPS. Use algo como `https://mobile.seudominio` no Studio; não use HTTP público para tráfego real.

## Configuração no QuestFlow Studio

1. Abra **Configurações → Mobile Cloud Bridge**.
2. Marque **Ativar Mobile Cloud Bridge**.
3. Informe a URL HTTPS pública.
4. Informe a mesma chave usada em `QUESTFLOW_BRIDGE_KEY`.
5. Escolha o intervalo (30 s é um bom ponto inicial) e o tamanho do pacote offline.
6. Clique **Salvar Mobile Cloud Bridge**.
7. Clique **Testar Gateway**.
8. Clique **Publicar e receber agora**.

## Aparelhos já pareados na 6.9.5

Ao atualizar o app para Mobile 0.3, abra-o uma vez com o Studio acessível. O `bootstrap` informa a URL Cloud e o aparelho a grava no SecureStore. Depois disso, ele pode alternar de rota automaticamente. Novos pareamentos já recebem a URL no QR.

## Teste operacional sugerido

1. Com Studio ligado, confirme no Perfil Mobile: **Studio local**.
2. Responda uma questão e sincronize.
3. Desligue o Studio ou saia da LAN.
4. Com Internet disponível, abra o app e confirme **Cloud Bridge**.
5. Responda outra questão; o feedback Cloud deverá ser marcado como provisório.
6. Reative o Studio.
7. No Studio, use **Publicar e receber agora** ou aguarde o ciclo automático.
8. Confirme que a fila remota volta a zero e que a resposta aparece no histórico/métricas definitivas.

## Dados persistidos pelo Gateway

- tenant/account/learner IDs técnicos;
- hashes das sessões Mobile ativas;
- projeções Mobile;
- pacote limitado de questões;
- material privado de feedback separado do payload público;
- eventos imutáveis aguardando o Studio;
- ações de desconexão pendentes.

Não são necessários `TURSO_AUTH_TOKEN`, banco SQLite do Studio, PDFs, chaves de IA ou acesso às tabelas internas.
