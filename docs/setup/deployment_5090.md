# Deploy do backend no host da RTX 5090

O host da GPU executa dois serviços separados na mesma rede Docker:

- `procelbot-ollama`: inferência local com `gemma4:26b`;
- `procelbot-chatbot`: API FastAPI, sem porta publicada no host.

O Caddy continua sendo a única entrada pelo Tunnel:

```text
api.procel-chatbot.com   → Caddy → chatbot:8000
ollama.procel-chatbot.com → Caddy → ollama:11434
admin.procel-chatbot.com → Caddy → painel + chatbot:8000
```

## Preparação

O checkout do projeto deve existir em `/opt/procelbot-backend`. A rede
`procelbot_internal` é criada pela stack do Ollama e reutilizada pelo backend.
Não execute `docker compose down` na stack do Ollama para publicar o backend.

Antes de preencher o `.env`, confirme a subnet atualmente atribuída à rede e
use exatamente esse valor em `TRUSTED_PROXY_NETWORKS`:

```bash
docker network inspect -f '{{(index .IPAM.Config 0).Subnet}}' \
  procelbot_internal
```

No host atual, o resultado é `172.24.0.0/16`. Não substitua esse valor por uma
rede ampla como `0.0.0.0/0`; se a rede for recriada no futuro, atualize o env e
reinicie o backend.

Crie o arquivo protegido:

```bash
install -d -m 750 /opt/procelbot-backend/deploy/backend/secrets
cp /opt/procelbot-backend/deploy/backend/backend.env.example \
  /opt/procelbot-backend/deploy/backend/secrets/backend.env
chmod 640 /opt/procelbot-backend/deploy/backend/secrets/backend.env
```

Para o Caddy, use [`proxy.env.example`](../../deploy/procelbot/proxy.env.example)
como modelo e crie `deploy/procelbot/secrets/proxy.env` no servidor. Preencha
`PROCELBOT_API_KEY` com o mesmo valor de `API_KEY` do backend.

Preencha `API_KEY` e `ADMIN_API_KEY` com valores diferentes. As duas chaves
ficam somente no servidor; o frontend usa apenas a `API_KEY` em
`X-API-Key`, enquanto operações administrativas usam `ADMIN_API_KEY`.

No proxy, `PROCELBOT_API_KEY` deve repetir somente o valor de `API_KEY` do
backend. O entrypoint encerra o Caddy se essa variável estiver ausente, para
que o Swagger não pareça protegido pelo Basic Auth enquanto o FastAPI rejeita
secretamente o header injetado.

O painel também exige `PROCELBOT_ADMIN_API_KEY`, que deve repetir
`ADMIN_API_KEY` do backend. Essa chave fica somente no `proxy.env` do host e é
injetada pelo Caddy no upstream de `/api/status`; ela nunca deve aparecer nos
assets estáticos ou no navegador.

O hash Basic Auth do proxy fica no arquivo separado
`/opt/procelbot/secrets/proxy-basic-auth.hash`, montado somente no container do
Caddy. Não coloque o hash no `proxy.env`, pois os cifrões do bcrypt podem ser
interpretados pelo Compose.

Como o backend e o Ollama estão na mesma rede Docker, o backend usa:

```env
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_USERNAME=
OLLAMA_PASSWORD=
```

O Basic Auth continua habilitado no endpoint público do Ollama para acessos
externos. O suporte a gateway remoto protegido permanece disponível quando o
backend for movido para outro host.

No host da RTX 5090, o serviço `ollama` deve declarar tanto `gpus: all` quanto
`runtime: nvidia` no Compose. O segundo campo é necessário neste Docker para
que o Ollama receba as bibliotecas NVIDIA e não faça fallback silencioso para
CPU. Depois de alterar essa configuração, recrie somente o serviço Ollama,
preservando o volume `procelbot_ollama_models`:

```bash
sudo docker compose -f /opt/procelbot/compose.yaml \
  up -d --force-recreate --no-deps ollama
```

Confirme `runtime=nvidia`, `ollama ps` com `size_vram > 0` e `nvidia-smi`
durante uma geração. A porta `11434` não deve ter publicação no host.

## Agente local de métricas

O agente roda no próprio host da RTX 5090, com o usuário limitado
`procelbot`. Ele não abre porta, não usa Gemini, não acessa o Docker socket e
somente atualiza o snapshot `/var/lib/procelbot/node-metrics/latest.json` a
cada 30 segundos. A consulta `nvidia-smi` lê telemetria do driver e não reserva
VRAM nem executa inferência.

Depois de sincronizar o checkout em `/opt/procelbot-backend`, instale o
diretório de saída e o unit file:

```bash
sudo install -d -o procelbot -g procelbot -m 755 \
  /var/lib/procelbot/node-metrics
sudo chown root:root \
  /opt/procelbot-backend/deploy/node_metrics/procelbot_node_metrics.py
sudo chmod 755 \
  /opt/procelbot-backend/deploy/node_metrics/procelbot_node_metrics.py
sudo install -o root -g root -m 644 \
  /opt/procelbot-backend/deploy/node_metrics/procelbot-node-metrics.service \
  /etc/systemd/system/procelbot-node-metrics.service
sudo systemctl daemon-reload
sudo systemctl enable --now procelbot-node-metrics.service
```

Recrie o container do backend para aplicar o bind mount somente leitura
definido no compose:

```bash
sudo systemctl restart procelbot-backend.service
```

Valide o agente sem expor o conteúdo do arquivo em logs públicos:

```bash
sudo systemctl is-active procelbot-node-metrics.service
sudo stat -c '%U:%G %a %n' /var/lib/procelbot/node-metrics/latest.json
sudo python3 -m json.tool /var/lib/procelbot/node-metrics/latest.json >/dev/null
```

O backend aceita o snapshot por até 60 segundos. Se o agente parar, o campo
`node_metrics.fresh` ficará falso quando o último snapshot for lido pelo
endpoint administrativo.

## Ponte de contexto canônico

O backend de produção não deve receber a credencial do PostgreSQL sem TLS.
Instale a [ponte local de contexto canônico](canonical_snapshot_bridge.md): o
sincronizador usa túnel SSH/VPN, transação `READ ONLY` e grava um snapshot
sanitizado. O Compose monta esse snapshot como `:ro` e compartilha apenas o GID
do grupo `procelbot-context`.

Antes de recriar o backend, defina `CANONICAL_SNAPSHOT_GID` no arquivo
`deploy/backend/.env` e remova `REMOTE_PG_PASSWORD` do `backend.env`. Se não
existir acesso SSH/bastion ou VPN até a origem, mantenha os endpoints canônicos
indisponíveis; não aponte o sincronizador diretamente para
`187.77.58.122:4343` com `sslmode=disable`.

## Publicação

Instale o unit file e suba o backend:

```bash
sudo install -m 644 deploy/backend/procelbot-backend.service \
  /etc/systemd/system/procelbot-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now procelbot-backend.service
```

Sincronize os arquivos versionados da borda com a stack existente. Não copie
`secrets/` do checkout: mantenha os segredos já instalados em `/opt/procelbot`.

```bash
cd /opt/procelbot-backend
sudo install -o root -g procelbot -m 640 deploy/procelbot/Caddyfile \
  /opt/procelbot/Caddyfile
sudo install -o root -g procelbot -m 640 deploy/procelbot/compose.yaml \
  /opt/procelbot/compose.yaml
sudo install -o root -g root -m 644 deploy/procelbot/caddy-entrypoint.sh \
  /opt/procelbot/caddy-entrypoint.sh
```

Depois, recrie somente o proxy para aplicar a rota `api.procel-chatbot.com`:

```bash
sudo docker compose -f /opt/procelbot/compose.yaml up -d --force-recreate proxy
```

O compose monta `deploy/procelbot/admin` em `/srv/admin` como somente leitura.
O painel usa `/api/status` na mesma origem, enquanto `/swagger` e
`/openapi.json` são proxied pelo Caddy com a chave pública da API.

## Cloudflare

O Tunnel mantém a rota do Ollama e da API e recebe uma terceira entrada:

```text
Hostname: admin.procel-chatbot.com
Service:  http://localhost:80
```

A rota existente de `ollama.procel-chatbot.com` permanece inalterada. Não
crie uma rota apontando diretamente para `8000` ou `11434`.

Crie uma aplicação Cloudflare Access do tipo `self-hosted` para
`admin.procel-chatbot.com`, usando política `Allow` somente para a identidade
administrativa definida na conta. One-time PIN é suficiente para a primeira
versão; não use `Everyone` ou `Bypass`.

No ingresso do Tunnel, habilite a validação de Access no origin com os valores
da organização e da aplicação criada:

```text
originRequest.access.required: true
originRequest.access.teamName: <TEAM_NAME>
originRequest.access.audTag: [<ACCESS_APPLICATION_AUD_TAG>]
```

O `cloudflared` valida a assinatura e a audiência antes de chegar ao Caddy;
este também responde 403 se o cabeçalho de asserção do Access não estiver
presente.

O DNS necessário é:

```text
Tipo: CNAME
Nome: admin
Destino: b89b38cd-58d4-4d41-8400-52d3107ee21d.cfargotunnel.com
Proxy: Proxied
TTL: Auto
```

O CNAME foi criado no dashboard e está publicado como registro de Tunnel
proxied. O token Cloudflare atualmente usado pelo checkout continua sem
`DNS Write`; para automatizar alterações futuras, use um token separado com
escopo mínimo `Zone DNS Edit`.

## Validação

Antes do Tunnel/DNS, valide que a borda local bloqueia o painel sem a asserção
do Access:

```bash
curl --fail --resolve api.procel-chatbot.com:80:127.0.0.1 \
  http://api.procel-chatbot.com/v1/health
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --resolve admin.procel-chatbot.com:80:127.0.0.1 \
  http://admin.procel-chatbot.com/)" = 403
```

Depois de publicar o hostname no Cloudflare, valide pela URL pública:

```bash
curl --fail https://api.procel-chatbot.com/v1/health
curl --fail https://api.procel-chatbot.com/v1/personas \
  -H 'X-API-Key: <API_KEY>'
# Após autenticar no Access pelo navegador, abra:
# https://admin.procel-chatbot.com/
```

O time autorizado no Cloudflare Access também pode abrir o laboratório de
notificações em:

```text
https://admin.procel-chatbot.com/notifications
```

O Studio usa contexto fictício e fixa `use_canonical_context=false`. Ele gera
candidatas reais no modelo local e permite aprovar/reprovar a fila, mas não
entrega push nem consulta o PostgreSQL remoto.

O smoke público atual deve mostrar redirecionamento 302 para o Cloudflare
Access quando não há sessão. Após o login autorizado, o painel deve carregar
e consultar `/api/status` sem enviar a `ADMIN_API_KEY` ao navegador.

O health deve indicar `provider=ollama`, `model=gemma4:26b` e
`provider_available=true`. Falhas de PostgreSQL ou Spring aparecem no bloco
`components` e não impedem a validação do runtime do Ollama.

Para Swagger, acesse `/docs` usando o mesmo usuário Basic Auth já configurado
para o proxy do Ollama. A senha nunca deve ser colocada no Git ou no frontend.

Para validar o endpoint administrativo direto, use a chave
`ADMIN_API_KEY` somente de uma máquina de operação confiável:

```bash
curl --fail https://api.procel-chatbot.com/v1/admin/status \
  -H 'X-API-Key: <ADMIN_API_KEY>'
```

Esse endpoint não deve ser chamado diretamente por um frontend público. O
painel atrás do Cloudflare Access faz a chamada por proxy server-side, sem
enviar a chave administrativa ao navegador.
