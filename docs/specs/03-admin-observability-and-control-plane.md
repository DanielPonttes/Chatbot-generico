# SPEC-003 — Observabilidade administrativa e plano de controle

**Status:** Accepted  
**Escopo:** primeira fatia do plano de operação segura e do futuro painel
restrito de Swagger/status.

## 1. Objetivo

Criar um contrato administrativo mínimo para que uma interface restrita possa
consultar o estado do backend sem transformar a API pública em um painel de
infraestrutura.

O painel futuro será uma aplicação separada, protegida na borda por Cloudflare
Access ou mecanismo equivalente. O navegador não receberá `ADMIN_API_KEY`,
tokens de Cloudflare, credenciais do Ollama ou credenciais das integrações.

## 2. Entrega desta iteração

### Endpoint protegido

```text
GET /v1/admin/status
Header: X-API-Key: <ADMIN_API_KEY>
```

Resposta resumida:

```json
{
  "service": "Procel Chatbot",
  "status": "healthy",
  "provider": "ollama",
  "model": "gemma4:26b",
  "provider_available": true,
  "components": {
    "database": "connected",
    "spring_api": "reachable (HTTP 200)"
  },
  "checked_at": "2026-08-10T12:00:00Z",
  "uptime_seconds": 123.456
}
```

O endpoint reaproveita as sondas existentes e permanece fora da superfície
pública. Ele não retorna IPs, caminhos, tokens, chaves, senhas, logs ou
métricas do host.

Nesta iteração, `/v1/health` mantém compatibilidade com o contrato anterior,
mas seus componentes públicos foram reduzidos a estados (`connected`,
`reachable` e equivalentes), sem nomes de banco ou outros detalhes de
identificação. Uma separação completa entre liveness e readiness continua
planejada para a próxima iteração.

## 3. Roadmap do plano de controle

### Fase A — backend (esta iteração)

- manter `GET /v1/health` como contrato público de liveness/compatibilidade;
- adicionar `GET /v1/admin/status` com a chave administrativa;
- documentar o schema no OpenAPI;
- cobrir 401, 403, sucesso e ausência de segredos nos testes.

### Fase B — automação de infraestrutura

- manter a integração da API Cloudflare em ferramenta administrativa separada;
- listar túnel, rotas e DNS usando token de conta com escopo mínimo;
- oferecer modo `--dry-run` antes de qualquer alteração;
- exigir confirmação explícita para criar, alterar ou remover rota;
- nunca carregar o token Cloudflare dentro do container FastAPI.

### Fase C — painel restrito

- subdomínio administrativo dedicado, ainda não publicado nesta etapa;
- proteção primária por Cloudflare Access;
- Swagger/ReDoc embutidos por mesma origem ou proxy server-side;
- chamadas administrativas feitas pelo servidor do painel, nunca pelo browser
  com `ADMIN_API_KEY`;
- polling de status em 15–30 segundos como primeira versão;
- SSE/WebSocket somente se houver necessidade real de atualização contínua.

### Fase D — métricas do host GPU (`SPEC-004`)

- agente mínimo separado para `nvidia-smi`, disco, memória e estados de
  serviços;
- snapshot local somente leitura consumido por `/v1/admin/status`;
- sem montar `/var/run/docker.sock` no FastAPI;
- retenção e agregação de métricas históricas continuam planejadas para o
  painel, enquanto a primeira versão usa apenas o snapshot atual.

Os detalhes do agente, do contrato e do rollback estão em
[`04-local-node-metrics-agent.md`](04-local-node-metrics-agent.md).

## 4. Critérios de aceite desta iteração

- `/v1/admin/status` rejeita ausência de chave com `401`;
- rejeita a chave pública com `403`;
- falha com `503` quando `ADMIN_API_KEY` não está configurada;
- aceita somente `ADMIN_API_KEY` e retorna `200`;
- o schema aparece no OpenAPI sob `/v1/admin/status`;
- a resposta não contém nomes de campos de segredo;
- falhas de integração continuam representadas como status resumido;
- nenhum token de Cloudflare é lido pelo processo FastAPI.

## 5. Segurança e rollback

O endpoint depende da mesma autenticação administrativa usada pelas mutações
sensíveis. A futura interface não deve usar a API pública como substituto de
Cloudflare Access.

Para rollback, remover a rota e o schema desta especificação e manter o
endpoint público `/v1/health`. Não alterar chaves ou configurações do Tunnel.
