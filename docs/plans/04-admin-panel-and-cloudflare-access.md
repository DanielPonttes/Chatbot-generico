# Plano 04 — Painel administrativo e Cloudflare Access

**Status:** Concluído  
**Base:** `SPEC-005`  
**Objetivo:** criar uma superfície restrita para operação sem expor chaves ao
navegador.

## Decisão

Reutilizar o Caddy existente como servidor estático e proxy server-side. Isso
evita mais um container e mantém o painel na mesma rede privada do backend.
Cloudflare Access será a autenticação de borda; o Caddy injeta as chaves apenas
no upstream e o backend mantém sua própria autorização.

## Etapas e checkpoints

| Etapa | Entrega | Checkpoint |
| --- | --- | --- |
| 1 | SPEC-005 e threat model | contrato revisado, sem segredos |
| 2 | Assets do painel | status, GPU e serviços sem chave no cliente |
| 3 | Proxy Caddy | `/api/status`, `/swagger` e `/openapi.json` server-side |
| 4 | Access | aplicação self-hosted e política allow restrita |
| 5 | Tunnel/DNS | hostname `admin.procel-chatbot.com` proxied |
| 6 | Deploy e smoke | Access sem sessão bloqueia; sessão autorizada carrega painel |
| 7 | Revisão | testes, gate e documentação de rollback |

## Configuração

- hostname: `admin.procel-chatbot.com`;
- upstream local: `http://localhost:80` pelo Tunnel;
- intervalo visual: 30 s;
- chave admin: somente `PROCELBOT_ADMIN_API_KEY` no `proxy.env` do host;
- histórico: fora do escopo desta etapa.

## Estado externo

O CNAME `admin` foi criado no dashboard como registro de Tunnel proxied. O
token Cloudflare usado para a automação continua sem permissão de DNS Zone
Edit, portanto alterações futuras de DNS exigirão dashboard ou token separado
com escopo mínimo.

## Rollback

1. remover o hostname do ingresso do Tunnel;
2. remover ou desativar a aplicação Access;
3. recriar o proxy sem o site `admin.procel-chatbot.com`;
4. remover `PROCELBOT_ADMIN_API_KEY` do `proxy.env` somente depois de parar o
   proxy que a utiliza;
5. manter `api.procel-chatbot.com`, Ollama e `/v1/admin/status` intactos.
