# Documentacao da API Backend

Backend em FastAPI. A composicao da aplicacao fica em `app/main.py`, as rotas em `app/api/routes.py`, os schemas em `app/models/schemas.py` e a logica de dominio em `app/services/`.

## Contrato público atual

O contrato novo usa o prefixo `/v1`. As rotas sem prefixo permanecem apenas
para compatibilidade temporária e devem ser desativadas antes da publicação.
Endpoints protegidos exigem o header `X-API-Key`; `/v1/health` e o OpenAPI são
exceções para monitoramento e descoberta do contrato. Swagger/ReDoc passam pela
mesma dependência e podem ser privados com `DOCS_PUBLIC=false`. A matriz de
acesso e as decisões de segurança estão em [SPEC-002](../specs/02-public-api-security-and-contracts.md).

Operações administrativas, como aprovar/remover notificações ou invocar um
endpoint Spring com efeito externo, exigem uma segunda chave no mesmo header,
configurada em `ADMIN_API_KEY`.

## Convencoes

- Respostas de erro usam `HTTPException` com `detail` estruturado quando possivel.
- `provider` em respostas de chat pode ser `google`, `ollama` ou `huggingface`.
- `model_override` troca o modelo apenas naquela requisicao.
- `POST /chat/proactive` salva automaticamente a notificacao gerada como `Pendente`.

## Health

### `GET /health`

Verifica a aplicacao e o provider LLM configurado.

Resposta:

```json
{
  "status": "healthy",
  "provider": "google",
  "model": "gemini-3-flash-preview",
  "provider_available": true,
  "message": null
}
```

`status` pode ser `healthy`, `degraded` ou `unhealthy`.

## Chat

### `POST /chat`

Entrada:

```json
{
  "session_id": "usuario-123",
  "message": "Ola, tudo bem?",
  "model_override": "gemini-3-pro-preview"
}
```

Campos:

- `session_id`: obrigatorio, 1 a 100 caracteres.
- `message`: obrigatorio, 1 a 4000 caracteres.
- `model_override`: opcional.

Resposta:

```json
{
  "session_id": "usuario-123",
  "reply": "Resposta do assistente",
  "provider": "google",
  "model": "gemini-3-pro-preview",
  "context_summary": null
}
```

## Personas e Perfis

### `GET /personas`

Lista tons disponiveis:

- `provocador`
- `motivador`
- `debochado`

### `GET /target-profiles`

Lista perfis-alvo:

- `gastao`
- `indiferente`
- `engajado`

### `GET /notifications/types`

Retorna os templates de notificação que o backend executa atualmente. O
catálogo é a fonte de descoberta para `notification_type_id` e para as chaves
obrigatórias de `notification_context`.

Exemplo resumido:

```json
[
  {
    "id": "feedback_alerta_consumo",
    "name": "Alerta de Consumo Anômalo",
    "category": "Feedback em Tempo Real",
    "subtype": "Alerta de Consumo Anômalo",
    "default_use_rag": false,
    "required_context_vars": [
      "anomaly_window",
      "measured_consumption_kwh",
      "expected_consumption_kwh"
    ],
    "context_variables": [
      "anomaly_percent",
      "anomaly_window",
      "expected_consumption_kwh",
      "measured_consumption_kwh",
      "recommended_action",
      "room_id"
    ]
  }
]
```

O catálogo não retorna o prompt interno. As missões do documento V3 usam o
mesmo objeto de contexto extensível, mas só serão publicadas como IDs de
missão executáveis depois que seus templates, fontes de dados e regras de
disparo forem normalizados. O endpoint de catálogo já publica a matriz
normalizada para integração; entradas sem template permanecem marcadas como
`catalog_only` e não podem gerar notificações.

### `GET /notifications/missions`

Retorna as 64 missões normalizadas do documento V3. Cada missão informa
`component_inputs`, `agent_inputs`, `context_variables`, `template_id` e
`execution_status`. A consulta individual usa
`GET /notifications/missions/{mission_id}`.

### `POST /notifications/generate`

Gera uma candidata a partir de `mission_id`, resolvendo automaticamente o
template técnico associado. Missões `catalog_only` respondem `409`; contexto
incompleto responde `400`. A saída mantém o formato de `ChatResponse` e a
notificação é salva como `Pendente` para revisão humana.

O campo opcional `use_canonical_context` ativa a resolução de `pessoa_id`,
`room_id` e `sensor_external_id` pelos contratos canônicos. Esse modo exige a
chave administrativa e uma origem PostgreSQL com TLS. Somente snapshots
`fresh` são usados; valores enviados que divirjam da fonte retornam
`409 canonical_context_conflict`. O assembler não inventa baseline, ranking,
recompensa, progresso ou consumo ausente, e o contexto final continua limitado
a 32 chaves e 8 KiB.

Erros específicos desse modo:

- `400 canonical_context_selector_required`: nenhum seletor canônico enviado;
- `400 canonical_context_limits_exceeded`: merge acima de 32 chaves ou 8 KiB;
- `404 context_not_found`: pessoa ou sala não encontrada;
- `409 canonical_context_conflict`: input diverge da fonte;
- `409 canonical_context_not_fresh`: snapshot `stale`, `empty` ou com clock skew;
- `503 context_source_unavailable`: TLS ausente, timeout ou origem indisponível.

Para evitar persistir PII ou telemetria, `prompt_used` fica nulo nas candidatas
geradas com contexto canônico. O backend registra apenas o ID técnico da
candidata, os nomes dos campos observados e os tipos de fonte, sem IDs de
pessoa, sala ou sensor.

## Chat Proativo e Notificacoes

### `POST /chat/proactive`

Gera uma notificacao curta, persiste no SQLite como `Pendente` e retorna o ID gerado em `session_id`.

Entrada completa:

```json
{
  "persona_id": "motivador",
  "target_profile_id": "engajado",
  "persona_override": {
    "description": "opcional",
    "system_prompt": "opcional"
  },
  "model_override": "gemini-3-flash-preview",
  "use_rag": true,
  "room_id": "2",
  "sensor_external_id": "SII-001",
  "pessoa_id": "ravilon",
  "notification_type_id": "reengajamento_streak",
  "notification_context": {
    "streak_days": 14,
    "hours_remaining": 3,
    "user_first_name": "Daniel"
  }
}
```

Campos importantes:

- `persona_id`: obrigatorio.
- `target_profile_id`: opcional.
- `use_rag`: opcional. Se `null`, segue o `default_use_rag` do tipo YAML; sem tipo, o padrao legado e `true`.
- `notification_type_id`: opcional. Deve existir em `app/services/notification_type.yaml`.
- `notification_context`: opcional. Deve conter as variáveis obrigatórias do tipo escolhido; consulte `/notifications/types`.
- `room_id`, `sensor_external_id`, `pessoa_id`: opcionais para contexto operacional.

Resposta:

```json
{
  "session_id": "f9c7c0c8-2f5f-4a3b-8f5f-6c0a6d4f3a11",
  "reply": "Mensagem push gerada",
  "provider": "google",
  "model": "gemini-3-flash-preview",
  "context_summary": "Sala Elevador (id=2) | Sensor SII-001"
}
```

Falhas comuns:

- persona inexistente: `404`.
- tipo de notificação inexistente: `404` (`notification_type_not_found`).
- variáveis obrigatórias ausentes no tipo: `400` (`validation_error`).
- provider LLM indisponivel: `500` ou `503`, dependendo da origem.

### `GET /notifications/saved`

Lista notificacoes salvas:

```json
[
  {
    "id": "uuid",
    "type": "Pendente",
    "content": "texto",
    "persona": "motivador",
    "model": "gemini-3-flash-preview",
    "date": "2026-05-12T02:00:00+00:00",
    "target_profile": "engajado",
    "prompt_used": "prompt completo"
  }
]
```

### `POST /notifications/saved`

Salva manualmente uma notificacao:

```json
{
  "type": "Pendente",
  "content": "Texto da notificacao",
  "persona": "motivador",
  "model": "gemini-3-flash-preview",
  "target_profile": "engajado",
  "prompt_used": "opcional"
}
```

`POST` sempre cria uma notificacao `Pendente`; `id` e `date` podem ser
enviados, mas se ausentes sao gerados no servidor. A aprovacao/reprovacao e a
remocao exigem `ADMIN_API_KEY` e devem usar os endpoints abaixo.

### `PATCH /notifications/saved/{notif_id}`

Atualiza avaliacao:

```json
{
  "type": "Aprovada"
}
```

Exige a chave administrativa.

Valores aceitos:

- `Pendente`
- `Aprovada`
- `Reprovada`

### `DELETE /notifications/saved/{notif_id}`

Remove uma notificacao. Exige a chave administrativa.

### `DELETE /notifications/saved/all`

Remove todas as notificacoes. Exige a chave administrativa.

## RAG

### `POST /rag/search`

Busca na base vetorial local.

Entrada:

```json
{
  "query": "economia de energia em horarios de pico",
  "k": 4
}
```

Resposta:

```json
{
  "results": [
    {
      "content": "chunk encontrado",
      "source": "arquivo.pdf",
      "page": 1,
      "score": 0.42
    }
  ],
  "query_echo": "economia de energia em horarios de pico"
}
```

## Integracoes Externas

As rotas abaixo usam `app/services/integration_catalog.py`.

### `GET /integrations/catalog` (somente `ADMIN_API_KEY`)

Retorna uma visao consolidada:

- conexao do PostgreSQL remoto;
- tabelas remotas catalogadas;
- conexao da API Spring;
- endpoints Spring catalogados;
- recomendacoes mais relevantes para o projeto.

### `GET /integrations/database/tables` (somente `ADMIN_API_KEY`)

Lista tabelas do PostgreSQL remoto com categoria, estimativa de linhas, relevancia e endpoint de preview.

### `GET /integrations/database/tables/{schema_name}/{table_name}` (somente `ADMIN_API_KEY`)

Detalha uma tabela remota, incluindo colunas, chaves primarias e referencias.

### `GET /integrations/database/tables/{schema_name}/{table_name}/rows` (somente `ADMIN_API_KEY`)

Parametros:

- `limit`: 1 a 100, padrao 25.
- `offset`: padrao 0.

Retorna amostra paginada de linhas, com `ADMIN_API_KEY`; colunas conhecidas de
credenciais e PII (`password`, `email`, `telefone`, `matricula`, `token`,
`hash` e variantes de caixa) são retornadas como `[redacted]`.

### `GET /integrations/spring/endpoints` (somente `ADMIN_API_KEY`)

Lista endpoints Spring Boot catalogados.

### `POST /integrations/spring/endpoints/{endpoint_id}/invoke`

Entrada:

```json
{
  "path_params": {
    "room_id": "2"
  },
  "query_params": {
    "limit": 10
  },
  "body": null
}
```

Retorna status HTTP, URL final, content type e dados retornados pelo endpoint remoto.

### Autocomplete de Contexto

Usados pela tela `/notifications`:

- `GET /integrations/context/rooms?query=&limit=20`
- `GET /integrations/context/sensors?query=&room_id=&limit=20`
- `GET /integrations/context/people?query=&limit=20` (somente `ADMIN_API_KEY`)

Resposta:

```json
[
  {
    "id": "2",
    "label": "Sala Elevador",
    "description": "Predio A",
    "metadata": {}
  }
]
```

### Contexto canônico read-only

As rotas versionadas abaixo consultam a fonte PostgreSQL e exigem a chave
administrativa nesta primeira fase. Todas retornam `metadata` com `source`,
`scope`, `observed_at`, `fetched_at`, `fresh` e `status` (`fresh`, `stale` ou
`empty`). Indisponibilidade retorna `503 context_source_unavailable` e escopo
inexistente retorna `404 context_not_found`.

- `GET /v1/context/users/{user_id}/profile`
- `GET /v1/context/users/{user_id}/activities?limit=50`
- `GET /v1/context/rooms/{room_id}/telemetry/latest`
- `GET /v1/context/sensors/{sensor_id}/telemetry/latest`
- `GET /v1/context/rooms/{room_id}/presence`
- `GET /v1/context/missions?active_only=true&limit=100`
- `GET /v1/context/rules/parameter-definitions?active_only=true&limit=100`

O perfil mínimo não retorna e-mail, telefone, matrícula ou senha. Presença é
agregada por sala e não retorna IDs de pessoas. Telemetria preserva nome e
unidade do parâmetro; quando não há medição, `data` é `null` e o estado é
`empty`, sem preencher zero artificialmente.

## Schemas Centrais

- `ChatRequest`
- `ChatResponse`
- `ProactiveChatRequest`
- `PersonaOverride`
- `RAGSearchRequest`
- `RAGSearchResponse`
- `SavedNotificationCreate`
- `SavedNotificationResponse`
- `NotificationTypeUpdate`
- `IntegrationsCatalogResponse`
- `RemoteDatabaseCatalogResponse`
- `SpringApiCatalogResponse`
- `ContextLookupOptionResponse`
- `ContextMetadata`
- `CanonicalUserProfileResponse`
- `CanonicalActivitiesResponse`
- `CanonicalTelemetryResponse`
- `CanonicalPresenceResponse`
- `CanonicalMissionsResponse`
- `CanonicalParameterDefinitionsResponse`

## Persistencia

- Notificacoes: `app/api/db.py`, tabela `saved_notifications`.
- Historico opcional: `app/services/memory.py`, habilitado com `USE_SQLITE=true`.
- Vetores RAG: `data/chroma_db/`.
