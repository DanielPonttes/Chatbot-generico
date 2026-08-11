# SPEC-002 — Segurança e contratos da API pública

**Status:** Accepted  
**Escopo:** primeira versão pública do backend FastAPI e do gateway que será
colocado atrás do Tunnel.

## 1. Objetivo

Proteger a superfície pública antes de liberar o agente para consumidores
externos e registrar um contrato estável para as próximas integrações de
notificações dinâmicas.

Esta especificação não expõe credenciais, não transforma a API remota em um
proxy genérico e não torna o Ollama um serviço público independente do
gateway.

## 2. Controles obrigatórios

| Controle | Desenvolvimento | Produção |
| --- | --- | --- |
| API key | opcional | obrigatória em `X-API-Key` |
| Chave administrativa | opcional | obrigatória para mutações sensíveis em `ADMIN_API_KEY` |
| CORS | pode usar `*` | lista explícita de origens |
| Rate limit | opcional | maior que zero; por processo/IP, com IP encaminhado apenas por proxy confiável |
| Hosts | locais/testes | somente hosts publicados |
| Headers de proxy | ignorados salvo configuração explícita | `TRUSTED_PROXY_NETWORKS` com a rede do gateway; obrigatório quando houver proxy |
| Corpo HTTP | validado pelos schemas | limitado por `MAX_REQUEST_BODY_BYTES` |
| Rotas sem `/v1` | compatibilidade | desativadas |
| `model_override` | permitido | desativado ou limitado a `ALLOWED_MODELS` |
| Swagger/ReDoc | disponíveis | `DOCS_PUBLIC=false`; liberar apenas na borda/rede administrativa |
| Ollama admin API | bloqueada no Caddy | bloqueada no Caddy |

O processo deve falhar ao iniciar em `ENVIRONMENT=production` se a API key,
CORS explícito, rate limit, allowlist de modelos, hosts seguros, rede de proxy
confiável ou proteção da documentação estiverem ausentes.

## 3. Autenticação e respostas de erro

As rotas versionadas usam:

```http
X-API-Key: <chave-fora-do-repositorio>
```

`GET /v1/health` e `GET /openapi.json` permanecem públicos para monitoramento
e descoberta do contrato. A documentação interativa passa pela dependência de
autenticação e, em produção, deve usar `DOCS_PUBLIC=false`, ficando disponível
somente pela camada de borda ou rede administrativa.

Falhas de autenticação retornam `401` com envelope estruturado. Configuração
ausente em produção retorna `503` e impede que a aplicação pareça pública sem
proteção.

## 4. Contrato de endpoints da versão 1

| Método | Caminho | Acesso inicial | Finalidade |
| --- | --- | --- | --- |
| GET | `/v1/health` | público | liveness/estado resumido |
| POST | `/v1/chat` | API key | conversa síncrona |
| GET | `/v1/personas` | API key | catálogo de personas |
| GET | `/v1/target-profiles` | API key | catálogo de perfis-alvo |
| GET | `/v1/notifications/types` | API key | catálogo de templates e variáveis |
| GET | `/v1/notifications/missions` | API key | catálogo versionado das missões |
| GET | `/v1/notifications/missions/{mission_id}` | API key | consultar uma missão |
| POST | `/v1/notifications/generate` | API key | gerar candidata por missão |
| POST | `/v1/chat/proactive` | API key | gerar notificação candidata |
| POST | `/v1/rag/search` | API key | busca controlada no RAG |
| GET | `/v1/notifications/saved` | API key | listar candidatos salvos |
| POST | `/v1/notifications/saved` | API key | salvar candidato/manual |
| PATCH | `/v1/notifications/saved/{id}` | chave administrativa | aprovar/reprovar |
| DELETE | `/v1/notifications/saved/{id}` | chave administrativa | remover um candidato |
| DELETE | `/v1/notifications/saved/all` | chave administrativa | limpeza em lote |
| GET | `/v1/integrations/catalog` | chave administrativa | catálogo de integrações |
| GET | `/v1/integrations/database/tables` | chave administrativa | catálogo PostgreSQL |
| GET | `/v1/integrations/database/tables/{schema}/{table}` | chave administrativa | metadados de tabela |
| GET | `/v1/integrations/database/tables/{schema}/{table}/rows` | chave administrativa | preview limitado |
| GET | `/v1/integrations/spring/endpoints` | chave administrativa | catálogo Spring |
| POST | `/v1/integrations/spring/endpoints/{id}/invoke` | chave administrativa | invocação allowlisted |
| GET | `/v1/integrations/context/rooms` | API key | autocomplete de salas |
| GET | `/v1/integrations/context/sensors` | API key | autocomplete de sensores |
| GET | `/v1/integrations/context/people` | chave administrativa | autocomplete sem PII |

As rotas sem `/v1` são compatibilidade temporária e não fazem parte do
contrato novo. Elas devem ser desligadas antes da publicação do backend.
As páginas HTML locais (`/`, `/notifications`, `/rag`) não são endpoints da
API versionada: continuam protegidas pela chave e podem ser abertas com uma
chave válida mesmo após o desligamento das rotas legadas.

## 5. Contratos de payload

### Chat

```json
{
  "session_id": "sessao-001",
  "message": "Explique esta medição.",
  "model_override": null
}
```

Limites atuais: `session_id` até 100 caracteres, `message` até 4000 e nome de
modelo até 100 caracteres. Em produção, `model_override` deve ser nulo ou
pertencer à allowlist configurada.

### Notificação proativa

```json
{
  "persona_id": "motivador",
  "target_profile_id": "engajado",
  "use_rag": true,
  "notification_type_id": "reengajamento_streak",
  "notification_context": {"streak_days": 14}
}
```

O servidor valida persona, tipo de notificação, tamanho do contexto e
variáveis obrigatórias antes de persistir o candidato como `Pendente`.

O catálogo `GET /v1/notifications/types` é a fonte de descoberta para os IDs
técnicos, categorias, subtipos e variáveis de cada template executável. O
`notification_context` é intencionalmente extensível para acomodar as missões
do documento de notificações: usuário e recompensas, missão e progresso,
localização, telemetria interna, contexto externo/baselines e ranking/conquistas.
Ele continua limitado a 32 chaves e 8 KiB serializados.

O documento V3 possui 64 missões de produto. Elas não são tratadas como 64
templates executáveis nesta etapa: uma missão só deve ganhar um ID técnico
quando tiver template versionado, fontes de dados e regras de disparo definidos.

O catálogo de missões agora registra a distinção entre entradas de outros
componentes (`component_inputs`) e entradas derivadas pelo agente
(`agent_inputs`). O endpoint dedicado de geração resolve o template pelo
`mission_id`; uma missão sem template retorna `409` e não chama o LLM.

O `POST /v1/notifications/saved` também só aceita `type: "Pendente"`; a
transição para `Aprovada` ou `Reprovada` passa pelo `PATCH` administrativo.

### Avaliação

```json
{"type": "Aprovada"}
```

Valores aceitos: `Pendente`, `Aprovada` e `Reprovada`.

## 6. Decisões pendentes para a próxima iteração

1. Substituir a API key única por identidade e escopos (`chat:write`,
   `notifications:review`, `integrations:read`).
2. Mover rate limit para uma camada compartilhada ou para o gateway/Cloudflare.
3. Criar endpoints de eventos/entrega de notificações sem expor operações de
   banco ao frontend.
4. Separar health liveness de readiness detalhado; o readiness não deve
   executar sondas externas para cada chamada pública.
5. Confirmar, com os revisores de produto, nomes finais dos recursos e
   versionamento dos payloads de notificação.
6. Normalizar as 64 missões do documento em um catálogo versionado antes de
   criar `mission_id` e endpoints de entrega.
7. Fechar fontes canônicas e autorização para perfil, pontuação, ranking,
   telemetria e estado persistente das missões.

O deploy atrás de Caddy/Tunnel deve preencher `TRUSTED_PROXY_NETWORKS` com a
rede real do gateway. O valor padrão vazio não aceita `X-Forwarded-For` nem
`X-Forwarded-Proto`, evitando falsificação de identidade por clientes diretos.

O `deploy/procelbot` mantém a stack do Ollama atrás de Basic Auth e bloqueia a
API administrativa de modelos. O backend FastAPI é uma stack separada que
reutiliza a rede Docker interna; o Caddy roteia `api.procel-chatbot.com` para o
FastAPI e `ollama.procel-chatbot.com` para o Ollama. O Ollama não substitui o
gateway FastAPI nem deve receber o tráfego da API `/v1`.

## 7. Critérios de aceite

- Requisições sem API key recebem `401` em produção nos endpoints protegidos.
- Operações destrutivas ou com efeitos externos rejeitam a chave geral e exigem
  `ADMIN_API_KEY`.
- A aplicação não inicia com configuração pública insegura.
- CORS não aceita `*` com credenciais em produção.
- Modelos fora da allowlist são rejeitados.
- Headers de segurança e limite de corpo aparecem nas respostas públicas.
- Corpos acima de `MAX_REQUEST_BODY_BYTES` recebem `413` antes da rota.
- `/v1` aparece no OpenAPI; rotas legadas podem ser desligadas.
- O OpenAPI expõe o catálogo de templates e schemas explícitos para o fluxo de
  revisão humana das notificações.
- O OpenAPI expõe o catálogo versionado de missões e a geração dedicada sem
  quebrar `/v1/chat/proactive`.
- Testes automatizados cobrem autenticação, CORS, rate limit, hosts, headers,
  allowlist e contratos básicos.

## 8. Rollback

Em caso de regressão, retornar `ENVIRONMENT=development`, manter as rotas
legadas temporariamente e reverter apenas as mudanças desta especificação.
Não remover a API key nem reutilizar credenciais de infraestrutura.
