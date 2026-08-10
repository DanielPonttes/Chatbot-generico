# Guia de Instalacao e Execucao



Este guia configura o Chatbot Generico localmente com API, frontend estatico, RAG, notificacoes, testes e integracoes remotas.



## Pre-requisitos



- Python 3.11+.

- `pip` e `venv`.

- Node.js 18+ e `npm`.

- Uma opcao de LLM:

  - Google Gemini com `GEMINI_API_KEY`;

  - Ollama local;

  - HuggingFace com `HF_TOKEN`.

- Para Playwright em Linux/WSL, talvez seja necessario instalar dependencias do Chromium com `--with-deps`.



## Instalacao Completa



```bash

git clone https://github.com/DanielPonttes/Chatbot-generico.git

cd Chatbot-generico



python -m venv .venv

```



Ative o ambiente:



```powershell

# Windows PowerShell

.\.venv\Scripts\Activate.ps1

```



```bash

# Linux/macOS

source .venv/bin/activate

```



Instale dependencias:



```bash

pip install -r requirements.txt

npm install

npx playwright install chromium

```



Em Linux/WSL:



```bash

sudo npx playwright install --with-deps chromium

```



## Configuracao



Crie o `.env`:



```bash

cp .env.example .env

```



### Gemini



```env

LLM_PROVIDER=google

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3-flash-preview

```



### Ollama



Instale e rode:



```bash

ollama serve

ollama pull gemma4:26b

```



Configure:



```env

LLM_PROVIDER=ollama

OLLAMA_BASE_URL=http://localhost:11434

OLLAMA_MODEL=gemma4:26b

```



### HuggingFace



```env

LLM_PROVIDER=huggingface

HF_TOKEN=
HF_MODEL=microsoft/DialoGPT-small

```



### Integracoes Remotas



As rotas de catalogo e contexto operacional usam:



```env

REMOTE_PG_HOST=srv1428963.hstgr.cloud

REMOTE_PG_PORT=5432

REMOTE_PG_USER=postgres

REMOTE_PG_PASSWORD=


REMOTE_PG_SSLMODE=prefer

REMOTE_PG_CONNECT_TIMEOUT=5

REMOTE_PG_MAX_LIMIT=100



REMOTE_SPRING_BASE_URL=http://srv1428963.hstgr.cloud:8080

REMOTE_SPRING_TIMEOUT_SECONDS=15

```



Se essas variaveis estiverem ausentes ou inacessiveis, o chat basico ainda pode funcionar, mas as rotas `/integrations/*` e o contexto operacional real podem retornar erro de disponibilidade.



## Execucao



```bash

uvicorn app.main:app --reload --port 8000

```



Rotas visuais:



- `http://localhost:8000/`

- `http://localhost:8000/notifications`

- `http://localhost:8000/rag`

- `http://localhost:8000/docs`

- `http://localhost:8000/redoc`



## Testes



### Pytest



```bash

.\.venv\Scripts\python.exe -m pytest

```



Linux/macOS:



```bash

.venv/bin/python -m pytest

```



### Playwright



```bash

npm run test:e2e

```



O `playwright.config.js` sobe o FastAPI em `http://127.0.0.1:8012` quando `PLAYWRIGHT_BASE_URL` nao esta definido.



Para usar um servidor ja aberto:



```bash

PLAYWRIGHT_BASE_URL=http://127.0.0.1:8000 npm run test:e2e

```



No PowerShell:



```powershell

$env:PLAYWRIGHT_BASE_URL="http://127.0.0.1:8000"

npm run test:e2e

```



## Dados Locais



Arquivos gerados em runtime:



- `data/db/saved_notifications.db`: notificacoes salvas.

- `data/conversations.db`: historico de conversa se `USE_SQLITE=true`.

- `data/chroma_db/`: base vetorial do RAG.



A pasta `data/` e ignorada pelo git.



## Estrutura de Pastas



```text

app/

  api/       # rotas e SQLite de notificacoes

  core/      # configuracoes

  models/    # schemas Pydantic

  rag/       # Chroma, ingestao e busca

  services/  # LLM, personas, integracoes, contexto operacional

  static/    # paginas HTML

docs/

tests/

.github/workflows/ci.yml

package.json

requirements.txt

```



## Problemas Comuns



- `No module named pytest`: ative o `.venv` e rode `pip install -r requirements.txt`.

- Gemini sem chave: confira `GEMINI_API_KEY` no `.env`.

- RAG falhando: confira `GEMINI_API_KEY` ou `GOOGLE_API_KEY`, pois embeddings usam Google.

- Ollama indisponivel: rode `ollama serve` e confirme o modelo com `ollama list`.

- PostgreSQL remoto indisponivel: confirme `REMOTE_PG_*`, rede e permissao.

- Playwright falhando no Linux: rode `sudo npx playwright install --with-deps chromium`.
