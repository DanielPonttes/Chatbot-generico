---
name: technical-manifest
overview: "Analyze `d:\\daniel\\Chatbot-generico\\` and produce a dependency-tree manifest: entry point(s), core logic layer, external dependencies (APIs/DB), and concrete input→output data-travel paths."
todos:
  - id: confirm-scope
    content: Confirm which subproject(s) under d:\daniel to include if there are multiple besides Chatbot-generico; current manifest covers Chatbot-generico only.
    status: pending
  - id: expand-manifest
    content: If needed, expand the manifest to include exact endpoint list + frontend call sites in app/static/*.html, and document any additional external services discovered.
    status: pending
isProject: false
---

# Technical Manifest (Dependency Tree + Data Flow)

## System identification

- **Project root**: `[d:\daniel\Chatbot-generico\](d:\daniel\Chatbot-generico\)`
- **Runtime type**: **FastAPI** HTTP API served by **Uvicorn**

## Entry Point (composition root)

- **ASGI app**: `[app/main.py](d:\daniel\Chatbot-generico\app\main.py)`
  - **Creates** `app = FastAPI(...)` and wires router + static pages.
  - **Startup** initializes saved-notifications DB via `init_db()`.
  - **Shutdown** closes LLM provider + memory manager.

Key wiring excerpt:

```41:117:d:\daniel\Chatbot-generico\app\main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ...
    from app.api.db import init_db
    init_db()
    
    yield
    
    await close_provider()
    close_memory_manager()

app = FastAPI(
    # ...
    lifespan=lifespan,
)

app.include_router(router, tags=["chat"])
```

## Core Logic Layer (application logic)

In this codebase, “use cases” are mostly embedded in the HTTP layer (`routes.py`) and a single application service (`PersonaService`). There is no separate `usecases/` module.

- **HTTP orchestration (acts like application layer)**: `[app/api/routes.py](d:\daniel\Chatbot-generico\app\api\routes.py)`
  - `/chat`: fetch session history → call LLM → persist history → return response.
  - `/chat/proactive`: call `PersonaService.generate_proactive_message` → return response.
  - `/rag/search`: query vector store → return chunks.
  - `/notifications/saved`*: CRUD over local SQLite table.
- **Persona / proactive message logic**: `[app/services/persona_service.py](d:\daniel\Chatbot-generico\app\services\persona_service.py)`
  - Persona + target profile selection.
  - Prompt composition.
  - Optional RAG context retrieval.
  - Calls LLM provider.
- **Conversation memory abstraction**: `[app/services/memory.py](d:\daniel\Chatbot-generico\app\services\memory.py)`
  - `MemoryManager` interface.
  - Implementations: in-memory vs SQLite conversation DB.
- **LLM provider abstraction (adapter behind interface)**: `[app/services/llm_provider.py](d:\daniel\Chatbot-generico\app\services\llm_provider.py)`
  - `LLMProvider` interface.
  - Implementations: Ollama (local HTTP), HuggingFace (cloud HTTP), Google Gemini (SDK).

## External Dependencies (APIs / Databases / SDKs)

### External network APIs

- **Ollama HTTP API (local)**
  - **Where**: `OllamaProvider.generate()` POSTs to `.../api/chat` and checks `.../api/tags`.
  - **Code**: `[app/services/llm_provider.py](d:\daniel\Chatbot-generico\app\services\llm_provider.py)`
- **HuggingFace Inference API (cloud)**
  - **Where**: `HuggingFaceProvider.generate()` POSTs to `https://api-inference.huggingface.co/models/{model}`.
  - **Code**: `[app/services/llm_provider.py](d:\daniel\Chatbot-generico\app\services\llm_provider.py)`
- **Google Gemini API (cloud, via SDK)**
  - **Where**: `GoogleGeminiProvider.generate()` uses `genai.Client(...).models.generate_content(...)`.
  - **Code**: `[app/services/llm_provider.py](d:\daniel\Chatbot-generico\app\services\llm_provider.py)`
- **Google embeddings API (cloud, via LangChain)**
  - **Where**: `GoogleGenerativeAIEmbeddings(..., google_api_key=...)` used to embed documents/queries.
  - **Code**: `[app/rag/vector_db.py](d:\daniel\Chatbot-generico\app\rag\vector_db.py)`

### Local persistence (databases/files)

- **SQLite: saved notifications DB**
  - **File path**: `data/db/saved_notifications.db` (overridable via `SQLITE_DB_PATH`).
  - **Code**: `[app/api/db.py](d:\daniel\Chatbot-generico\app\api\db.py)`
- **SQLite: conversation history DB (optional)**
  - **File path**: `./data/conversations.db` (overridable via `SQLITE_PATH`; enabled via `USE_SQLITE=true`).
  - **Code**: `[app/services/memory.py](d:\daniel\Chatbot-generico\app\services\memory.py)`
- **Chroma vector store (local on disk)**
  - **Directory**: `data/chroma_db/`.
  - **Code**: `[app/rag/vector_db.py](d:\daniel\Chatbot-generico\app\rag\vector_db.py)`

### Config / secrets

- **Settings loader**: `[app/core/config.py](d:\daniel\Chatbot-generico\app\core\config.py)`
  - Loads from `.env` and environment variables.
  - **Security note**: there is a stray line containing what looks like a Google API key literal directly in source:

```56:66:d:\daniel\Chatbot-generico\app\core\config.py
# Configurações Google Gemini
# ==========================================
gemini_api_key: str | None = None
"REDACTED_GEMINI_API_KEY"
```

## Technical manifest: Dependency Tree (input → output)

```text
FastAPI_App (app/main.py)
├─ Lifespan
│  ├─ init_db() -> SQLite(saved_notifications)
│  └─ shutdown: close_provider(), close_memory_manager()
├─ Router (app/api/routes.py)
│  ├─ POST /chat
│  │  ├─ Input DTO: ChatRequest (app/models/schemas.py)
│  │  ├─ Memory: get_memory_manager() -> MemoryManager
│  │  │  ├─ InMemoryManager (RAM)
│  │  │  └─ SQLiteMemoryManager -> SQLite(conversations.db)
│  │  ├─ Provider: get_llm_provider() -> LLMProvider
│  │  │  ├─ OllamaProvider -> HTTP(Ollama /api/chat)
│  │  │  ├─ HuggingFaceProvider -> HTTP(HF Inference API)
│  │  │  └─ GoogleGeminiProvider -> SDK(Gemini generate_content)
│  │  ├─ Side effects
│  │  │  ├─ memory.add_message(user)
│  │  │  └─ memory.add_message(assistant)
│  │  └─ Output DTO: ChatResponse
│  │
│  ├─ POST /chat/proactive
│  │  ├─ Input DTO: ProactiveChatRequest
│  │  ├─ PersonaService.generate_proactive_message()
│  │  │  ├─ Persona/TargetProfile selection
│  │  │  ├─ Optional RAG
│  │  │  │  └─ get_relevant_context() -> Chroma(similarity_search)
│  │  │  │     └─ Embeddings: GoogleGenerativeAIEmbeddings (API key)
│  │  │  └─ provider.generate(prompt)
│  │  └─ Output DTO: ChatResponse
│  │
│  ├─ POST /rag/search
│  │  ├─ Input DTO: RAGSearchRequest
│  │  ├─ search_with_metadata()
│  │  │  └─ Chroma.similarity_search_with_score()
│  │  └─ Output DTO: RAGSearchResponse(results[])
│  │
│  └─ /notifications/saved*
│     ├─ get_all_saved_notifications()
│     ├─ save_notification(...)
│     ├─ delete_notification(id)
│     └─ clear_all_notifications()
│        └─ SQLite(saved_notifications.db)
└─ Static UI (app/static/*.html)
   └─ Browser fetch() -> calls the endpoints above
```

## Data travel: concrete paths

### 1) `/chat` (interactive chat)

- **Input**: HTTP `POST /chat` JSON (`ChatRequest.session_id`, `.message`, optional `.model_override`).
- **Data path**:

```54:90:d:\daniel\Chatbot-generico\app\api\routes.py
async def chat(request: ChatRequest) -> ChatResponse:
    provider = get_llm_provider()
    memory = get_memory_manager()
    history = memory.get_formatted_history(request.session_id)
    reply = await provider.generate(request.message, history, model_override=request.model_override)
    memory.add_message(request.session_id, "user", request.message)
    memory.add_message(request.session_id, "assistant", reply)
    used_model = request.model_override if request.model_override else provider.model
    return ChatResponse(
        session_id=request.session_id,
        reply=reply,
        provider=provider.name,
        model=used_model,
    )
```

- **External hops** (depending on provider):
  - **Ollama** POST `.../api/chat` (local) (`app/services/llm_provider.py` L146-L166)
  - **HuggingFace** POST `https://api-inference.huggingface.co/models/...` (`app/services/llm_provider.py` L370-L410)
  - **Gemini** SDK `generate_content` (`app/services/llm_provider.py` L280-L286)
- **Output**: HTTP 200 JSON `ChatResponse`.

### 2) `/chat/proactive` (persona message generation)

- **Input**: HTTP `POST /chat/proactive` JSON (`persona_id`, optional overrides, optional `use_rag`).
- **Data path**:
  - Controller delegates to persona service:

```169:195:d:\daniel\Chatbot-generico\app\api\routes.py
async def chat_proactive(request: ProactiveChatRequest) -> ChatResponse:
    message = await PersonaService.generate_proactive_message(
        request.persona_id,
        target_profile_id=request.target_profile_id,
        persona_override=request.persona_override,
        model_override=request.model_override,
        use_rag=request.use_rag,
    )
    provider = get_llm_provider()
    used_model = request.model_override if request.model_override else provider.model
    return ChatResponse(session_id="new-session", reply=message, provider=provider.name, model=used_model)
```

- Service composes prompt, optionally enriches with RAG, then calls provider:

```111:176:d:\daniel\Chatbot-generico\app\services\persona_service.py
async def generate_proactive_message(..., use_rag: bool = True) -> str:
    persona = PersonaService.get_persona_by_id(persona_id)
    # ... build target_context ...
    provider = get_llm_provider()
    # ... apply persona_override ...
    rag_context = ""
    if use_rag:
        retrieved_docs = get_relevant_context(rag_query, k=3)
        # ... embed into prompt ...
    prompt = (f"Atue com a seguinte persona:\n{system_prompt}\n{target_context}\n{rag_context}\n" ...)
    message = await provider.generate(prompt, model_override=model_override)
    return message
```

- **Output**: HTTP 200 JSON `ChatResponse`.

### 3) `/rag/search` (RAG dashboard)

- **Input**: HTTP `POST /rag/search` JSON (`query`, `k`).
- **Data path**:

```270:289:d:\daniel\Chatbot-generico\app\api\routes.py
async def semantic_search(request: RAGSearchRequest) -> RAGSearchResponse:
    results = search_with_metadata(request.query, k=request.k)
    return RAGSearchResponse(results=results, query_echo=request.query)
```

- **Vector store retrieval** (local Chroma on disk):

```22:49:d:\daniel\Chatbot-generico\app\rag\retriever.py
def search_with_metadata(query: str, k: int = 4) -> List[Dict[str, Any]]:
    vector_store = get_vector_store()
    results = vector_store.similarity_search_with_score(query, k=k)
    # ... format metadata ...
    return formatted_results
```

### 4) `/notifications/saved*` (saved notifications)

- **Input**: HTTP requests from frontend.
- **Data path**: routes call into SQLite helpers in `[app/api/db.py](d:\daniel\Chatbot-generico\app\api\db.py)` using `sqlite3.connect(DB_PATH)`.

## Notes / risks that affect dependency mapping

- **Gemini SDK package mismatch risk**: code imports `from google import genai` (newer Gemini SDK) but many projects pin `google-generativeai`; if you see runtime import errors, this is why.
- **Hardcoded secret in source**: the stray API key line in `app/core/config.py` should be removed and supplied via `.env` instead (even though it’s not assigned, it is still exposed in repo/text scans).

