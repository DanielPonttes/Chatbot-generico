# Plano 02 — Observabilidade administrativa e plano de controle

**Status:** Concluído — implementação, revisão e publicação remota validadas  
**Data:** 2026-08-10  
**Base:** `SPEC-002` aceita e backend publicado na RTX 5090.

## Objetivo

Preparar a operação segura do agente e a futura área restrita que reunirá
Swagger, contratos e status do servidor em tempo real.

## Princípios

- o backend de inferência continua na RTX 5090;
- a API pública não recebe credenciais de infraestrutura;
- o token Cloudflare fica em ferramenta administrativa separada;
- status público é mínimo; readiness detalhado exige chave administrativa;
- métricas do host não justificam montar Docker socket no backend;
- cada alteração de rota/DNS passa por plano, dry-run e revisão.

## Entregas e checkpoints

| Etapa | Entrega | Evidência | Estado |
| --- | --- | --- | --- |
| 1 | Contrato `GET /v1/admin/status` | testes 401/403/503/200 e schema OpenAPI | Concluída |
| 2 | Auditor Cloudflare read-only | túnel, rotas e zona consultados pela API | Concluída |
| 3 | CLI Cloudflare com dry-run | testes sem alteração e confirmação explícita | Pendente |
| 4 | Painel administrativo restrito | Cloudflare Access + proxy server-side | Futuro |
| 5 | Agente de métricas da RTX 5090 | `SPEC-004`, snapshot local sem Docker socket no FastAPI | Concluída |

## Evidência de conclusão da etapa 1

- `pytest`: 77 passed, 1 warning legado do `TestClient`/httpx;
- gate dos revisores: `GATE: PASS`;
- backend publicado e reiniciado na RTX 5090;
- `/v1/health`: `200` público;
- `/openapi.json`: `200` público;
- `/v1/admin/status`: `401` sem chave;
- OpenAPI marca health como público e status admin como protegido.
- `SPEC-004`: coletor local ativo na RTX 5090, snapshot fresco exposto somente
  no status administrativo.

## Próximas decisões

1. Definir o subdomínio administrativo, por exemplo `admin.procel-chatbot.com`.
2. Confirmar os usuários/grupos autorizados no Cloudflare Access.
3. Escolher se o painel será um frontend separado ou uma aplicação servida pelo
   Caddy na mesma rede Docker.
4. Definir retenção das métricas de GPU e histórico de incidentes.
5. Separar, em uma iteração posterior, escopos da API pública (`chat:write`,
   `notifications:review`, `integrations:read`) da chave administrativa.

## Gate de revisão

Antes de publicar o painel ou criar um novo hostname:

- executar `pytest`;
- executar `scripts/agent_review.sh gate --run-tests` com foco em autenticação,
  observabilidade e segredos;
- validar a configuração do Caddy e o Tunnel por smoke test público;
- registrar rollback e evidência da configuração Cloudflare.
