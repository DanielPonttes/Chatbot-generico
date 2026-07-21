# Chatbot Generico

Chatbot em FastAPI com chat interativo, geracao de notificacoes proativas, personas, RAG, persistencia SQLite, catalogo de integracoes externas e testes automatizados.

## Visao Geral

O projeto serve tres interfaces HTML estaticas pelo proprio FastAPI:

- `/`: chat principal.
- `/notifications`: gerador e avaliador de notificacoes proativas.
- `/rag`: visualizador de busca semantica na base vetorial.

O backend tambem expoe endpoints JSON para chat, saude, RAG, notificacoes salvas e exploracao das integracoes remotas com PostgreSQL e API Spring Boot.

## Principais Recursos

- Chat com historico por `session_id`.
- Providers LLM: Google Gemini, Ollama e HuggingFace.
- Override de modelo por requisicao.
- Personas fixas: `provocador`, `motivador`, `debochado`.
- Perfis-alvo: `gastao`, `indiferente`, `engajado`.
- Tipos de notificacao configurados em `app/services/notification_type.yaml`.
- Enriquecimento de notificacoes com contexto operacional real: sala, sensor, pessoa e medicoes (via API Spring Boot, com fallback direto no PostgreSQL remoto quando a API estiver indisponivel).
- RAG com Chroma e embeddings do Gemini.
- Persistencia de notificacoes em SQLite.
- Catalogo de tabelas PostgreSQL remotas e endpoints Spring Boot (com autenticacao JWT via `/api/auth/login`).
- Testes de API com pytest e E2E com Playwright.
- CI em GitHub Actions.

## Requisitos

- Python 3.11+.
- Node.js 18+ para Playwright.
- Uma das opcoes de LLM:
  - `GEMINI_API_KEY` para Google Gemini.
  - Ollama local.
  - `HF_TOKEN` para HuggingFace.
- Para RAG com embeddings do Google, configure `GEMINI_API_KEY` ou `GOOGLE_API_KEY`.
- Para contexto operacional remoto, configure as variaveis `REMOTE_PG_*` e `REMOTE_SPRING_BASE_URL`.

## Instalacao

```bash
git clone https://github.com/DanielPonttes/Chatbot-generico.git
cd Chatbot-generico

python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
npm install
npx playwright install chromium
```

`requirements.txt` e o caminho recomendado para rodar a aplicacao completa. O `pyproject.toml` contem a configuracao de pacote e dependencias principais, mas o projeto operacional usa as dependencias completas do `requirements.txt`.

## Configuracao

Crie um `.env` a partir de `.env.example`:

```bash
cp .env.example .env
```

Variaveis principais:

| Variavel | Uso |
| --- | --- |
| `LLM_PROVIDER` | `google`, `ollama` ou `huggingface`. |
| `GEMINI_API_KEY` | Chave do Gemini para chat, RAG e embeddings. |
| `GEMINI_MODEL` | Modelo Gemini padrao, como `gemini-3-flash-preview`. |
| `OLLAMA_BASE_URL` | URL local do Ollama. |
| `OLLAMA_MODEL` | Modelo local, como `qwen2.5:0.5b`. |
| `HF_TOKEN` | Token HuggingFace. |
| `HF_MODEL` | Modelo HuggingFace. |
| `MEMORY_MAX_MESSAGES` | Quantidade maxima de mensagens por sessao. |
| `USE_SQLITE` | Persistencia opcional do historico de conversa. |
| `SQLITE_PATH` | Caminho do SQLite de conversas. |
| `SQLITE_DB_PATH` | Caminho opcional do SQLite de notificacoes salvas. |
| `REMOTE_PG_*` | Credenciais e limites do PostgreSQL remoto. |
| `REMOTE_SPRING_BASE_URL` | URL base da API Spring Boot remota (ex: `https://procel.servehttp.com`). |
| `REMOTE_SPRING_USERNAME` | E-mail de login da API Spring (`POST /api/auth/login`). |
| `REMOTE_SPRING_PASSWORD` | Senha de login da API Spring. O JWT é cacheado e renovado automaticamente. |
| `API_KEY` | Chave de acesso da API (header `X-API-Key`). Vazia = aberta (dev). |
| `CORS_ALLOW_ORIGINS` | Origens CORS separadas por virgula. `*` libera tudo (dev). |
| `RATE_LIMIT_PER_MINUTE` | Limite de requisicoes/min por IP. `0` desativa. |

Exemplo minimo com Gemini:

```env
LLM_PROVIDER=google
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3-flash-preview
```

Exemplo com Ollama:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b
```

## Execucao

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse:

- Chat: `http://localhost:8000/`
- Notificacoes: `http://localhost:8000/notifications`
- RAG: `http://localhost:8000/rag`
- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Fluxo de Notificacoes

`POST /chat/proactive` gera uma notificacao curta e a salva automaticamente como `Pendente`.

O prompt final pode combinar:

- persona;
- perfil-alvo;
- tipo de notificacao YAML;
- variaveis dinamicas do tipo;
- contexto operacional remoto;
- RAG opcional;
- override temporario de system prompt;
- override de modelo.

Exemplo:

```bash
curl -X POST http://localhost:8000/chat/proactive \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "motivador",
    "target_profile_id": "engajado",
    "notification_type_id": "reengajamento_streak",
    "notification_context": {
      "streak_days": 14,
      "hours_remaining": 3,
      "user_first_name": "Daniel"
    },
    "room_id": "2",
    "sensor_external_id": "SII-001",
    "pessoa_id": "ravilon",
    "use_rag": true
  }'
```

Resposta resumida:

```json
{
  "session_id": "uuid-da-notificacao",
  "reply": "Mensagem gerada",
  "provider": "google",
  "model": "gemini-3-flash-preview",
  "context_summary": "Resumo do contexto aplicado"
}
```

Depois a notificacao pode ser avaliada:

```bash
curl -X PATCH http://localhost:8000/notifications/saved/{id} \
  -H "Content-Type: application/json" \
  -d '{"type": "Aprovada"}'
```

## Endpoints Principais

| Metodo | Rota | Descricao |
| --- | --- | --- |
| `GET` | `/health` | Saude da aplicacao e provider LLM. |
| `POST` | `/chat` | Chat interativo com historico. |
| `GET` | `/personas` | Lista personas. |
| `GET` | `/target-profiles` | Lista perfis-alvo. |
| `POST` | `/chat/proactive` | Gera notificacao e salva como pendente. |
| `POST` | `/rag/search` | Busca semantica direta. |
| `GET` | `/notifications/saved` | Lista notificacoes salvas. |
| `POST` | `/notifications/saved` | Salva notificacao manualmente. |
| `PATCH` | `/notifications/saved/{id}` | Atualiza status para `Pendente`, `Aprovada` ou `Reprovada`. |
| `DELETE` | `/notifications/saved/{id}` | Remove uma notificacao. |
| `DELETE` | `/notifications/saved/all` | Remove todas as notificacoes. |
| `GET` | `/integrations/catalog` | Catalogo consolidado do PostgreSQL e Spring. |
| `GET` | `/integrations/database/tables` | Lista tabelas remotas. |
| `GET` | `/integrations/database/tables/{schema}/{table}` | Detalha tabela remota. |
| `GET` | `/integrations/database/tables/{schema}/{table}/rows` | Amostra linhas da tabela. |
| `GET` | `/integrations/spring/endpoints` | Lista endpoints Spring catalogados. |
| `POST` | `/integrations/spring/endpoints/{endpoint_id}/invoke` | Invoca endpoint Spring suportado. |
| `GET` | `/integrations/context/rooms` | Autocomplete de salas. |
| `GET` | `/integrations/context/sensors` | Autocomplete de sensores. |
| `GET` | `/integrations/context/people` | Autocomplete de pessoas. |

## Estrutura

```text
app/
  api/
    db.py                 # SQLite de notificacoes salvas
    routes.py             # Endpoints HTTP
  core/
    config.py             # Pydantic Settings
  models/
    schemas.py            # DTOs Pydantic
  rag/
    ingest.py             # Ingestao de documentos
    retriever.py          # Busca semantica
    vector_db.py          # Chroma + embeddings
  services/
    integration_catalog.py # PostgreSQL remoto + Spring Boot
    llm_provider.py        # Gemini, Ollama, HuggingFace
    memory.py              # Memoria de conversa
    notification_type.yaml # Templates de notificacao
    persona_service.py     # Personas e prompt final
    proactive_context.py   # Contexto operacional real
  static/
    index.html
    notifications.html
    rag.html
docs/
tests/
```

## Testes

API:

```bash
.\.venv\Scripts\python.exe -m pytest
```

Ou em Linux/macOS:

```bash
.venv/bin/python -m pytest
```

E2E:

```bash
npm run test:e2e
```

Com navegador visivel:

```bash
npm run test:e2e:headed
```

## CI

O workflow `.github/workflows/ci.yml` roda em `push` e `pull_request`:

- `Pytest`
- `Playwright E2E`

Para detalhes de protecao de branch, veja `docs/setup/ci.md`.

## Documentacao Adicional

- `docs/setup/installation.md`: instalacao e execucao.
- `docs/backend/api.md`: referencia de API.
- `docs/frontend/interfaces.md`: telas HTML.
- `docs/services/llm_personas.md`: services, personas e notificacoes.
- `docs/setup/ci.md`: CI e protecao de branch.
- `docs/docs_for_ai/technical_summary_1703.md`: manifesto tecnico e fluxo de dados.

## Observacoes de Producao

- Autenticacao opcional por API key: defina `API_KEY` e os endpoints passam a exigir o header `X-API-Key` (exceto `/health` e docs, publicos para monitoramento).
- CORS configuravel via `CORS_ALLOW_ORIGINS` (padrao `*`; restrinja em producao).
- Rate limit por IP via `RATE_LIMIT_PER_MINUTE` (contador em memoria, por worker).
- Rotas versionadas sob `/v1` (ex: `/v1/chat`, `/v1/health`). Caminhos legados sem prefixo seguem ativos, ocultos do OpenAPI, e serao deprecados.
- O `/health` reporta o estado dos componentes externos (PostgreSQL e API Spring) no campo `components`.
- Erros inesperados retornam envelope padrao `{"detail": {"error": "internal_error", "message": ...}}`.
- Dados sensiveis devem ficar em `.env`, nunca versionados.
- O banco SQLite e os dados locais ficam em `data/`, que e ignorado pelo git.
- O RAG depende de chave Google para embeddings.
