# Technical Manifest

## System

- Runtime: FastAPI served by Uvicorn.
- Entry point: `app/main.py`.
- Router: `app/api/routes.py`.
- Schemas: `app/models/schemas.py`.
- Services: `app/services/`.
- Static UI: `app/static/`.

## Startup and Shutdown

`app/main.py` creates the FastAPI app, registers CORS, serves static pages and includes the API router.

Lifespan:

1. Logs configured provider, model and memory mode.
2. Initializes saved-notifications SQLite via `app.api.db.init_db()`.
3. On shutdown, closes the LLM provider and memory manager.

Static routes:

- `/` -> `index.html`
- `/notifications` -> `notifications.html`
- `/rag` -> `rag.html`

## Core Dependency Tree

```text
FastAPI app
├─ app.api.routes
│  ├─ /chat
│  │  ├─ get_memory_manager()
│  │  ├─ get_llm_provider()
│  │  └─ ChatResponse
│  ├─ /chat/proactive
│  │  ├─ PersonaService.generate_proactive_message()
│  │  ├─ save_notification()
│  │  └─ ChatResponse
│  ├─ /rag/search
│  │  └─ search_with_metadata()
│  ├─ /notifications/saved*
│  │  └─ app.api.db SQLite helpers
│  └─ /integrations/*
│     └─ integration_catalog services
├─ app.services.llm_provider
│  ├─ GoogleGeminiProvider
│  ├─ OllamaProvider
│  └─ HuggingFaceProvider
├─ app.services.persona_service
│  ├─ static personas
│  ├─ static target profiles
│  ├─ notification_type.yaml
│  ├─ proactive_context
│  ├─ optional RAG
│  └─ selected LLM provider
├─ app.rag
│  ├─ Chroma vector store
│  └─ Google embeddings
└─ app.static
   └─ browser fetch() calls API endpoints
```

## Main Data Paths

### `POST /chat`

Input:

- `session_id`
- `message`
- optional `model_override`

Flow:

1. `routes.chat()` loads memory via `get_memory_manager()`.
2. It retrieves formatted history for the session.
3. It calls `provider.generate(message, history, model_override=...)`.
4. It stores user and assistant messages.
5. It returns `ChatResponse`.

External dependency:

- Gemini, Ollama or HuggingFace, depending on `LLM_PROVIDER`.

### `POST /chat/proactive`

Input:

- `persona_id`
- optional `target_profile_id`
- optional `persona_override`
- optional `model_override`
- optional `use_rag`
- optional `room_id`
- optional `sensor_external_id`
- optional `pessoa_id`
- optional `notification_type_id`
- optional `notification_context`

Flow:

1. `routes.chat_proactive()` calls `PersonaService.generate_proactive_message()`.
2. `PersonaService` resolves the persona.
3. It resolves target profile when provided.
4. It loads `notification_type.yaml` templates and validates required context variables.
5. It formats the notification-type template with `notification_context`.
6. It asks `proactive_context.py` for real operational context.
7. It retrieves RAG context when enabled.
8. It calls the selected LLM provider.
9. It returns `ProactiveMessageResult`.
10. The route saves the notification as `Pendente` through `save_notification()`.
11. It returns `ChatResponse` with `session_id` equal to the saved notification ID.

Side effects:

- writes to `saved_notifications` SQLite table.

### `POST /rag/search`

Input:

- `query`
- `k`

Flow:

1. `routes.semantic_search()` calls `search_with_metadata()`.
2. `retriever.py` opens the Chroma vector store.
3. Chroma runs similarity search with Google embeddings.
4. Results are formatted as `RAGSearchResult`.

External dependency:

- Google embeddings API through LangChain when embedding/querying.

### `/integrations/*`

Flow:

1. Routes call `get_remote_postgres_catalog_service()` or `get_spring_api_catalog_service()`.
2. PostgreSQL routes introspect tables and optionally preview rows.
3. Spring routes list known endpoints and optionally invoke supported endpoints.
4. Context routes return autocomplete options for rooms, sensors and people.

External dependencies:

- PostgreSQL remote configured by `REMOTE_PG_*`.
- Spring Boot remote configured by `REMOTE_SPRING_BASE_URL`.

### `/notifications/saved*`

Flow:

1. Routes call `app.api.db` helpers.
2. Helpers use `sqlite3` with `DB_PATH`.
3. `DB_PATH` defaults to `data/db/saved_notifications.db`, overridable with `SQLITE_DB_PATH`.

Supported statuses:

- `Pendente`
- `Aprovada`
- `Reprovada`

## External Dependencies

### Network

- Gemini SDK: chat provider.
- Ollama local HTTP API.
- HuggingFace inference API.
- Google embeddings through LangChain.
- PostgreSQL remote.
- Spring Boot remote.

### Local Files

- `.env`: configuration.
- `data/db/saved_notifications.db`: saved notifications.
- `data/conversations.db`: optional conversation memory.
- `data/chroma_db/`: Chroma vector store.
- `app/services/notification_type.yaml`: notification templates.

## Test Coverage

Pytest:

- `tests/test_api.py`
- `tests/test_integrations_api.py`
- `tests/test_proactive_context.py`

Playwright:

- `tests/e2e/notifications.spec.js`
- `tests/e2e/helpers/notifications-mocks.js`

## Current Integration Notes

- Branches merged into local `main`: `feat-endpoint-consume`, `FEAT-Notifications`, `feat-reengagingNotification`.
- `criando-docker`, `feat-profiles-hax` and `feat-persona` were already represented in `main`.
- `PyYAML` is required because notification types are loaded from YAML.
- The README and docs describe the current merged behavior after conflict resolution.
