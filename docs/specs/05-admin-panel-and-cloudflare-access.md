# SPEC-005 — Painel administrativo e Cloudflare Access

**Status:** Accepted  
**Escopo:** primeira interface restrita para Swagger e status operacional.

**Estado de rollout:** o DNS público resolve, visitantes sem sessão recebem
302 para o Cloudflare Access e o smoke autenticado pelo navegador foi
confirmado.

## 1. Objetivo

Disponibilizar `admin.procel-chatbot.com` como uma interface de operação
protegida por Cloudflare Access, com atualização do status da RTX 5090 e acesso
ao Swagger sem enviar `ADMIN_API_KEY` ao navegador.

## 2. Arquitetura escolhida

Nesta primeira versão não é necessário um segundo container. O Caddy existente
serve os arquivos estáticos do painel e atua como proxy server-side:

```text
browser ── Cloudflare Access ── Tunnel ── Caddy :80
                                           ├─ /          → arquivos estáticos
                                           ├─ /api/status → chatbot:8000/v1/admin/status
                                           ├─ /swagger    → chatbot:8000/docs
                                           └─ /openapi.json → chatbot:8000/openapi.json
```

O Caddy injeta `PROCELBOT_ADMIN_API_KEY` somente na chamada para
`/api/status`. Para Swagger, injeta a `PROCELBOT_API_KEY` pública no upstream
do backend. As duas chaves ficam em `proxy.env` no host e nunca são incluídas
nos assets estáticos.

## 3. Cloudflare Access

Criar uma aplicação `self_hosted` para o destino público
`admin.procel-chatbot.com`, com política `allow` limitada ao e-mail/grupo
administrativo definido na conta. Não usar `Everyone`, `Bypass` ou um token de
serviço para o acesso humano ao painel.

O Tunnel recebe uma entrada adicional para
`admin.procel-chatbot.com → http://localhost:80`. O CNAME deve ser proxied e o
Access deve ser aplicado ao hostname completo. A proteção de borda não
substitui a `ADMIN_API_KEY`: o Caddy e o backend continuam com autenticação
server-side para evitar acesso acidental caso uma rota seja chamada sem a
sessão do Access.

O ingresso administrativo do Tunnel usa `originRequest.access.required=true`,
com o `teamName` da organização e o `audTag` da aplicação. Assim, o
`cloudflared` valida a asserção assinada antes de encaminhar a requisição; o
Caddy também rejeita requisições administrativas que não tragam essa asserção.

## 4. Superfície do painel

- `/`: resumo do runtime, provider/modelo, uptime, CPU, memória, disco, GPU e
  estados Docker/backend/Ollama/cloudflared;
- `/api/status`: rota interna do painel, sem chave no cliente;
- `/swagger`: Swagger do backend na mesma origem;
- `/openapi.json`: contrato OpenAPI usado pelo Swagger.

A rota de Swagger é intencionalmente exata (`/swagger`); a UI carrega o contrato
pela rota separada `/openapi.json`.

O painel usa polling de 30 segundos, não armazena histórico e não altera
recursos do servidor. Histórico, gráficos e ações administrativas exigem uma
especificação posterior.

## 5. Segurança e critérios de aceite

- visitante não autenticado não recebe o HTML do painel;
- a política Access permite somente a identidade administrativa definida;
- `ADMIN_API_KEY` não aparece no HTML, CSS, JavaScript, OpenAPI ou respostas do
  painel;
- `/api/status` funciona apenas através do proxy server-side;
- Swagger carrega na origem do painel sem expor chaves ao browser;
- `X-Frame-Options`, CSP, `no-store` e remoção de cookies no upstream estão
  ativos;
- o Tunnel valida o JWT do Access por audiência antes do origin;
- a rota pública `api.procel-chatbot.com` mantém os mesmos contratos;
- rollback remove a entrada do Tunnel, a aplicação Access, o site Caddy e o
  bind dos assets, sem alterar o backend nem o agente de métricas.
