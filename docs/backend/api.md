# Documentacao da API Backend

Backend em FastAPI. A composicao da aplicacao fica em `app/main.py`, as rotas em `app/api/routes.py`, os schemas em `app/models/schemas.py` e a logica de dominio em `app/services/`.

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
- `notification_context`: opcional. Deve conter as variaveis obrigatorias do tipo escolhido.
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
- tipo de notificacao inexistente: `404`.
- variaveis obrigatorias ausentes no tipo: `404` com mensagem do `ValueError`.
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
  "type": "Aprovada",
  "content": "Texto da notificacao",
  "persona": "motivador",
  "model": "gemini-3-flash-preview",
  "target_profile": "engajado",
  "prompt_used": "opcional"
}
```

`id` e `date` podem ser enviados, mas se ausentes sao gerados no servidor.

### `PATCH /notifications/saved/{notif_id}`

Atualiza avaliacao:

```json
{
  "type": "Aprovada"
}
```

Valores aceitos:

- `Pendente`
- `Aprovada`
- `Reprovada`

### `DELETE /notifications/saved/{notif_id}`

Remove uma notificacao.

### `DELETE /notifications/saved/all`

Remove todas as notificacoes.

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

### `GET /integrations/catalog`

Retorna uma visao consolidada:

- conexao do PostgreSQL remoto;
- tabelas remotas catalogadas;
- conexao da API Spring;
- endpoints Spring catalogados;
- recomendacoes mais relevantes para o projeto.

### `GET /integrations/database/tables`

Lista tabelas do PostgreSQL remoto com categoria, estimativa de linhas, relevancia e endpoint de preview.

### `GET /integrations/database/tables/{schema_name}/{table_name}`

Detalha uma tabela remota, incluindo colunas, chaves primarias e referencias.

### `GET /integrations/database/tables/{schema_name}/{table_name}/rows`

Parametros:

- `limit`: 1 a 100, padrao 25.
- `offset`: padrao 0.

Retorna amostra paginada de linhas.

### `GET /integrations/spring/endpoints`

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
- `GET /integrations/context/people?query=&limit=20`

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

## Persistencia

- Notificacoes: `app/api/db.py`, tabela `saved_notifications`.
- Historico opcional: `app/services/memory.py`, habilitado com `USE_SQLITE=true`.
- Vetores RAG: `data/chroma_db/`.
