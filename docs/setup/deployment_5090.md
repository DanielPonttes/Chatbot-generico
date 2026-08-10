# Deploy do backend no host da RTX 5090

O host da GPU executa dois serviços separados na mesma rede Docker:

- `procelbot-ollama`: inferência local com `gemma4:26b`;
- `procelbot-chatbot`: API FastAPI, sem porta publicada no host.

O Caddy continua sendo a única entrada pelo Tunnel:

```text
api.procel-chatbot.com   → Caddy → chatbot:8000
ollama.procel-chatbot.com → Caddy → ollama:11434
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

## Publicação

Instale o unit file e suba o backend:

```bash
sudo install -m 644 deploy/backend/procelbot-backend.service \
  /etc/systemd/system/procelbot-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now procelbot-backend.service
```

Depois, recarregue o Caddy para aplicar a rota `api.procel-chatbot.com`:

```bash
sudo docker compose -f /opt/procelbot/compose.yaml up -d --force-recreate proxy
```

## Cloudflare

O Tunnel precisa de uma segunda aplicação/hostname apontando para:

```text
Hostname: api.procel-chatbot.com
Service:  http://localhost:80
```

A rota existente de `ollama.procel-chatbot.com` permanece inalterada. Não
crie uma rota apontando diretamente para `8000` ou `11434`.

## Validação

Antes do Tunnel/DNS, valide a borda localmente no host da GPU:

```bash
curl --fail --resolve api.procel-chatbot.com:80:127.0.0.1 \
  http://api.procel-chatbot.com/v1/health
```

Depois de publicar o hostname no Cloudflare, valide pela URL pública:

```bash
curl --fail https://api.procel-chatbot.com/v1/health
curl --fail https://api.procel-chatbot.com/v1/personas \
  -H 'X-API-Key: <API_KEY>'
```

O health deve indicar `provider=ollama`, `model=gemma4:26b` e
`provider_available=true`. Falhas de PostgreSQL ou Spring aparecem no bloco
`components` e não impedem a validação do runtime do Ollama.

Para Swagger, acesse `/docs` usando o mesmo usuário Basic Auth já configurado
para o proxy do Ollama. A senha nunca deve ser colocada no Git ou no frontend.
