# 🌱 EcoApp — Notificações Inteligentes com RAG

> FastAPI com geração de notificações proativas guiadas por personas, suporte a múltiplos provedores LLM e busca semântica via RAG (Retrieval-Augmented Generation).

---

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Estrutura de Diretórios](#estrutura-de-diretórios)
- [Lógica do Projeto](#lógica-do-projeto)
  - [Provedores LLM](#provedores-llm)
  - [Sistema de Personas](#sistema-de-personas)
  - [RAG — Base de Conhecimento](#rag--base-de-conhecimento)
  - [Memória de Conversa](#memória-de-conversa)
  - [Persistência de Feedback](#persistência-de-feedback)
- [API — Endpoints](#api--endpoints)
- [Frontend Estático](#frontend-estático)
- [Fluxos Principais](#fluxos-principais)
- [Pré-requisitos](#pré-requisitos)
- [Instalação e Configuração](#instalação-e-configuração)
  - [1. Clonar o Repositório](#1-clonar-o-repositório)
  - [2. Python e Ambiente Virtual](#2-python-e-ambiente-virtual)
  - [3. Variáveis de Ambiente (.env)](#3-variáveis-de-ambiente-env)
  - [4. Instalar Dependências](#4-instalar-dependências)
- [Rodando o Projeto](#rodando-o-projeto)
  - [Opção A — Uvicorn (direto)](#opção-a--uvicorn-direto)
  - [Opção B — Docker](#opção-b--docker)
- [Ollama — LLM Local](#ollama--llm-local)
- [Ingestão de PDFs no RAG](#ingestão-de-pdfs-no-rag)
- [Testes](#testes)
- [Observações Importantes](#observações-importantes)

---

## Visão Geral

O EcoApp é um hub de **eficiência energética** que usa LLMs para gerar **push notifications personalizadas** para diferentes perfis de usuários. O sistema combina:

- **Personas** com tons de voz distintos (provocador, motivador, debochado)
- **Perfis-alvo** que descrevem o comportamento do usuário final (gastador, indiferente, engajado)
- **RAG** com base vetorial construída a partir de PDFs sobre eficiência energética
- **Múltiplos provedores LLM**: Ollama (local), HuggingFace (remoto) ou Google Gemini
- **Frontend vanilla** (3 páginas HTML/JS/CSS) servido pelo próprio FastAPI para testes e visualização

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                        Cliente (Browser)                    │
│         index.html   notifications.html   rag.html          │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP
┌───────────────────────────▼─────────────────────────────────┐
│                      FastAPI  (app/main.py)                  │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  /chat      │  │ /chat/       │  │  /rag/search      │  │
│  │  /health    │  │  proactive   │  │  /notifications/  │  │
│  │  /personas  │  │ /target-     │  │   saved (CRUD)    │  │
│  └──────┬──────┘  │  profiles   │  └────────┬──────────┘  │
│         │         └──────┬───────┘           │             │
│  ┌──────▼──────────────────▼────┐    ┌───────▼──────────┐  │
│  │       LLM Provider           │    │  ChromaDB (RAG)  │  │
│  │  Ollama │ HuggingFace │Gemini│    │  + Google Embed. │  │
│  └──────────────────────────────┘    └──────────────────┘  │
│                                                             │
│  ┌───────────────────┐   ┌──────────────────────────────┐  │
│  │  Memory Manager   │   │     SQLite (2 bancos)        │  │
│  │  RAM ou SQLite    │   │  conversations.db            │  │
│  └───────────────────┘   │  saved_notifications.db      │  │
│                          └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Estrutura de Diretórios

```
.
├── app/
│   ├── main.py                  # Entrypoint FastAPI, lifecycle, páginas estáticas
│   ├── core/
│   │   └── config.py            # Settings via pydantic-settings + .env
│   ├── api/
│   │   ├── routes.py            # Todos os endpoints HTTP
│   │   └── db.py                # SQLite para saved notifications
│   ├── models/
│   │   └── schemas.py           # Contratos Pydantic (requests/responses)
│   ├── services/
│   │   ├── llm_provider.py      # Abstração LLM + Ollama, HuggingFace, Gemini
│   │   ├── memory.py            # Histórico de conversa (RAM ou SQLite)
│   │   └── persona_service.py   # Personas, perfis-alvo, geração proativa
│   ├── rag/
│   │   ├── vector_db.py         # ChromaDB persistente + embeddings Google
│   │   ├── retriever.py         # Funções de busca semântica
│   │   └── ingest.py            # Script CLI de ingestão de PDFs
│   └── static/
│       ├── index.html           # Hub principal
│       ├── notifications.html   # Gerador de notificações proativas
│       └── rag.html             # Visualizador de busca RAG
├── data/
│   ├── chroma_db/               # Base vetorial persistida (gerada pelo ingest)
│   ├── db/
│   │   └── saved_notifications.db
│   └── conversations.db         # Histórico de chat (se use_sqlite=true)
├── tests/
│   ├── conftest.py
│   └── test_api.py
├── docs/                        # Documentação interna e planos
├── scripts/                     # Scripts utilitários de manutenção (não são runtime)
├── prototypes/
│   └── EcoApp Mobile.html       # Protótipo de app mobile (sem integração backend)
├── .env.example                 # Template de configuração
├── requirements.txt
└── pyproject.toml
```

---

## Lógica do Projeto

### Provedores LLM

O projeto abstrai a geração de texto por meio de uma interface `LLMProvider` (ABC), com três implementações intercambiáveis via variável de ambiente `LLM_PROVIDER`:

**Ollama** (`"ollama"`) — Recomendado para desenvolvimento local
- Comunica-se com um servidor Ollama local via `POST /api/chat`
- Injeta o system prompt global como role `"system"` na conversa
- Verifica disponibilidade do modelo via `GET /api/tags`
- Suporta `model_override` por requisição

**HuggingFace** (`"huggingface"`) — API remota
- Usa a HuggingFace Inference API
- Monta um prompt textual unificado (não usa chat nativo)
- Inclui as últimas 4 mensagens do histórico para não estourar contexto

**Google Gemini** (`"google"`) — API remota - Mais utilizado
- Usa o SDK `google-genai` (`from google import genai`)
- Simula chat convertendo histórico para o formato `contents` do SDK
- O system prompt é "fixado" como primeiro par user/model na conversa

Todos os providers retornam exceções tipadas:
- `ProviderNotAvailableError` → HTTP 503
- `ModelNotFoundError` → HTTP 503
- `LLMProviderError` → HTTP 500

---

### Sistema de Personas

O `PersonaService` centraliza a lógica de geração de notificações proativas. Ele combina três dimensões:

**Personas** (tom de voz do bot):
| ID | Nome | Comportamento |
|---|---|---|
| `provocador` | Provocador | Desafia o usuário, ironia leve, frases curtas |
| `motivador` | Motivador | Extremamente positivo, emojis, linguagem inspiradora |
| `debochado` | Debochado | Sarcástico, informal, humor e gírias |

**Perfis-alvo** (contexto do usuário final):
| ID | Nome | Descrição |
|---|---|---|
| `gastao` | Gastão | Desperdiça energia, indiferente ao consumo |
| `indiferente` | Indiferente | Ignora notificações do app |
| `engajado` | Engajado | Já economiza e quer otimizar ainda mais |

**Fluxo de montagem do prompt proativo:**
1. Seleciona persona → define `system_prompt` (aplicando override se fornecido)
2. Se `target_profile_id` presente → injeta bloco `CONTEXTO DO USUÁRIO ALVO`
3. Se `use_rag=true` → busca os 3 trechos mais relevantes no ChromaDB e injeta em `<BASE_DE_CONHECIMENTO>`
4. Pede ao LLM uma notificação push de 1 a 2 frases

> ⚠️ **System prompt em camadas:** O Ollama injeta adicionalmente o `BOT_SYSTEM_PROMPT` global. O PersonaService embute o system prompt da persona dentro do próprio prompt textual. Isso cria duas camadas de instrução que podem ser desejadas (redundância intencional) ou causar conflito dependendo do modelo.

---

### RAG — Base de Conhecimento

O módulo RAG (`app/rag/`) implementa busca semântica em documentos PDF sobre eficiência energética.

**Componentes:**

- **`vector_db.py`**: ChromaDB persistente em `data/chroma_db/`, usando `GoogleGenerativeAIEmbeddings` com o modelo `gemini-embedding-001`. A chave de API do Google é **sempre necessária** para embeddings, independentemente do provider LLM escolhido.

- **`retriever.py`**: Expõe duas funções:
  - `get_relevant_context(query, k)` → retorna string concatenada para injeção no prompt
  - `search_with_metadata(query, k)` → retorna lista de dicts com `content`, `source`, `page` e `score` (para o dashboard)

- **`ingest.py`**: Script CLI para popular a base vetorial. Divide cada PDF em chunks de 1000 caracteres (overlap de 200) usando `RecursiveCharacterTextSplitter`, e insere em lotes de 50 com pausa de 65 segundos entre lotes (para respeitar cotas do tier gratuito do Google).

---

### Memória de Conversa

O `MemoryManager` (ABC) tem duas implementações:

- **`InMemoryManager`**: `defaultdict(list)` por `session_id`, mantém apenas as últimas N mensagens em RAM. Não persiste entre restarts.
- **`SQLiteMemoryManager`**: Tabela `messages` com `session_id`, `role`, `content` e `timestamp`. Ao inserir, deleta mensagens além do limite por sessão. Persiste entre restarts.

A escolha é feita via `USE_SQLITE=true/false` no `.env`.

---

### Persistência de Feedback

O módulo `app/api/db.py` mantém um SQLite separado (`data/db/saved_notifications.db`) para registrar o feedback (like/dislike) dos usuários sobre as notificações geradas. Cada registro contém o texto da notificação, a persona usada, o modelo, o tipo de feedback e a data.

---

## API — Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/chat` | Chat com histórico e memória de sessão |
| `GET` | `/health` | Status do provider LLM (`healthy/degraded/unhealthy`) |
| `GET` | `/personas` | Lista de personas disponíveis |
| `GET` | `/target-profiles` | Lista de perfis-alvo disponíveis |
| `POST` | `/chat/proactive` | Gera notificação proativa com persona + RAG |
| `POST` | `/rag/search` | Busca semântica direta no ChromaDB |
| `GET` | `/notifications/saved` | Lista notificações salvas com feedback |
| `POST` | `/notifications/saved` | Salva uma notificação com feedback |
| `DELETE` | `/notifications/saved/{id}` | Remove uma notificação salva |
| `DELETE` | `/notifications/saved/all` | Limpa todas as notificações salvas |
| `GET` | `/docs` | Swagger UI (documentação interativa) |
| `GET` | `/redoc` | ReDoc UI |

**Páginas estáticas:**
| Rota | Arquivo |
|---|---|
| `GET /` | `app/static/index.html` |
| `GET /notifications` | `app/static/notifications.html` |
| `GET /rag` | `app/static/rag.html` |

---

## Frontend Estático

O frontend é composto por 3 páginas vanilla HTML/JS/CSS, sem framework, usando Tailwind CSS e Lucide Icons via CDN.

**`index.html` — Hub Principal**
- Cards de navegação para as outras páginas
- Modal de configurações globais: modelo preferencial, toggle de RAG
- Indicador de status online/offline (polling `/health` a cada 15s)
- Tema dark/light persistido em `localStorage`

**`notifications.html` — Gerador de Notificações**
- Selects dinâmicos de persona e perfil-alvo (carregados via API)
- Textarea para override do system prompt da persona
- Exibe a notificação gerada + botões de like/dislike
- Modal "Salvas" com abas (aprovadas/reprovadas) e CRUD completo

**`rag.html` — Visualizador RAG**
- Campo de query e seletor de `k` (número de resultados)
- Cards com chunk retornado, fonte, página e score/distância

---

## Fluxos Principais

### Chat Normal (`POST /chat`)
```
Cliente → POST /chat
  → get_memory_manager() → busca histórico da sessão
  → get_llm_provider() → provider.generate(mensagem, histórico)
  → salva user+assistant no memory manager
  → retorna ChatResponse
```

### Notificação Proativa (`POST /chat/proactive`)
```
notifications.html
  → GET /personas + GET /target-profiles (popula selects)
  → POST /chat/proactive
      → PersonaService.generate_proactive_message()
          → monta system prompt da persona
          → injeta contexto do perfil-alvo
          → [opcional] get_relevant_context() → ChromaDB
          → provider.generate(prompt_completo)
      → retorna ChatResponse
```

### Busca RAG (`POST /rag/search`)
```
rag.html → POST /rag/search
  → search_with_metadata(query, k) → ChromaDB
  → retorna lista de chunks com source/page/score
```

### Feedback (`POST /notifications/saved`)
```
notifications.html
  → like/dislike → POST /notifications/saved
  → insere em saved_notifications.db
  → GET /notifications/saved → lista no modal
```

---

## Pré-requisitos

- **Instalações no Windows ou MAC podem variar, mas suportamos todas as plataformas através do Docker**
- **Linux** (Ubuntu 20.04+ recomendado)
- **Python 3.10+**
- **pip** e **venv**
- **Git**
- Para LLM local: **Docker** ou binário do **Ollama**
- Para RAG e provider Gemini: **chave de API do Google**

---

## Instalação e Configuração

### 1. Clonar o Repositório

```bash
git clone <https://github.com/DanielPonttes/Chatbot-generico.git>

```

---

### 2. Python e Ambiente Virtual

```bash
# Verificar versão do Python (precisa ser 3.10+)
python3 --version

# Criar ambiente virtual
python3 -m venv .venv

# Ativar o ambiente virtual
source .venv/bin/activate

# Confirmar que está no venv
which python  # deve apontar para .venv/bin/python
```

---

### 3. Variáveis de Ambiente (.env)

Copie o arquivo de exemplo e preencha conforme seu provider:

```bash
cp .env.example .env
```

Edite o `.env`:

```dotenv
# ── Servidor ──────────────────────────────────
APP_NAME="EcoApp"
DEBUG=false

# ── Provider LLM ──────────────────────────────
# Opções: "ollama" | "huggingface" | "google"
LLM_PROVIDER=ollama

# ── Ollama (para LLM_PROVIDER=ollama) ─────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# ── HuggingFace (para LLM_PROVIDER=huggingface)
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
HF_MODEL=mistralai/Mistral-7B-Instruct-v0.2

# ── Google Gemini (para LLM_PROVIDER=google) ──
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_MODEL=gemini-3-flash-preview

# ── RAG (sempre necessário para embeddings) ───
# Usa GEMINI_API_KEY acima; ou defina GOOGLE_API_KEY
# GOOGLE_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── Bot ───────────────────────────────────────
BOT_SYSTEM_PROMPT="Você é um assistente de eficiência energética."

# ── Memória ───────────────────────────────────
MEMORY_MAX_MESSAGES=20
USE_SQLITE=false
SQLITE_PATH=./data/conversations.db

# ── Saved Notifications ───────────────────────
SQLITE_DB_PATH=./data/db/saved_notifications.db
```

> **Importante:** A chave do Google (`GEMINI_API_KEY` ou `GOOGLE_API_KEY`) é necessária para os embeddings do RAG, mesmo que você use Ollama como provider de geração.

---

### 4. Instalar Dependências

```bash
# Com o venv ativado:
pip install --upgrade pip
pip install -r requirements.txt
```

Criar diretórios de dados necessários:

```bash
mkdir -p data/db data/chroma_db
```

---

## Rodando o Projeto

### Opção A — Uvicorn (direto)

```bash
# Ativar o venv (se ainda não estiver)
source .venv/bin/activate

# Rodar em modo desenvolvimento (com hot-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Rodar em modo produção
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

A aplicação estará disponível em:
- **Hub:** http://localhost:8000
- **Notificações:** http://localhost:8000/notifications
- **RAG:** http://localhost:8000/rag
- **Swagger:** http://localhost:8000/docs

---

### Opção B — Docker - Recomendado

**Usando Dockerfile** (crie um `Dockerfile` na raiz se não existir):

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/db data/chroma_db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Build e execução:**

```bash
# Build da imagem
docker build -t ecoapp:latest .

# Rodar o container (com .env e volumes para persistência)
docker run -d \
  --name ecoapp \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ecoapp:latest

# Ver logs
docker logs -f ecoapp

# Parar
docker stop ecoapp

# Remover
docker rm ecoapp
```

**Usando Docker Compose** (`docker-compose.yml`):

```yaml
version: "3.9"

services:
  ecoapp:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped

  # Opcional: Ollama como serviço
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

volumes:
  ollama_data:
```

```bash
# Subir tudo
docker compose up -d

# Se estiver usando Ollama via Docker Compose, ajuste o .env:
# OLLAMA_BASE_URL=http://ollama:11434

# Ver logs
docker compose logs -f ecoapp

# Derrubar
docker compose down
```

---

## Ollama — LLM Local

O Ollama permite rodar modelos LLM localmente sem depender de APIs externas.

### Instalação do Ollama

```bash
# Instalar via script oficial
curl -fsSL https://ollama.com/install.sh | sh

# Verificar instalação
ollama --version
```

### Iniciar o servidor Ollama

```bash
# Rodar o servidor em background
ollama serve &

# Ou como serviço systemd (após instalação)
sudo systemctl start ollama
sudo systemctl enable ollama  # para iniciar com o sistema
```

### Baixar um modelo

```bash
# Modelos recomendados (bom equilíbrio velocidade/qualidade)
ollama pull llama3          # ~4.7GB — Meta Llama 3 8B
ollama pull mistral         # ~4.1GB — Mistral 7B
ollama pull gemma2          # ~5.4GB — Google Gemma 2 9B

# Modelo mais leve (para máquinas menos potentes)
ollama pull phi3:mini       # ~2.3GB — Microsoft Phi-3 Mini

# Listar modelos baixados
ollama list

# Testar o modelo interativamente
ollama run llama3
```

### Configurar no .env

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

### Ollama via Docker

```bash
# CPU apenas
docker run -d --name ollama \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama

# Com GPU NVIDIA
docker run -d --gpus=all --name ollama \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama

# Baixar modelo dentro do container
docker exec -it ollama ollama pull llama3
```

---

## Ingestão de PDFs no RAG

Para popular a base vetorial com documentos sobre eficiência energética:

```bash
# Ativar venv
source .venv/bin/activate

# Ingerir um ou mais PDFs
python -m app.rag.ingest caminho/para/documento1.pdf caminho/para/documento2.pdf

# Exemplo com múltiplos arquivos de uma pasta
python -m app.rag.ingest docs/pdfs/*.pdf
```

> ⚠️ A ingestão usa a API de embeddings do Google. Com o tier gratuito, o script faz pausas automáticas de 65 segundos entre lotes de 50 chunks para respeitar os rate limits. Para grandes volumes de documentos, prefira executar fora do horário de pico ou use uma conta paga.

A base vetorial é salva em `data/chroma_db/` e é carregada automaticamente pelo servidor. Para reindexar do zero, delete a pasta `data/chroma_db/` e execute o ingest novamente.

---

## Testes

```bash
# Ativar venv
source .venv/bin/activate

# Instalar dependências de teste (se necessário)
pip install pytest pytest-asyncio httpx

# Rodar todos os testes
pytest tests/ -v

# Rodar com output detalhado
pytest tests/ -v --tb=short

# Rodar apenas um arquivo de testes
pytest tests/test_api.py -v
```

Os testes usam mocks para o provider LLM e o memory manager, portanto **não requerem** Ollama, HuggingFace ou Gemini rodando.

> ⚠️ **Inconsistência conhecida:** O teste `test_root_returns_welcome_message` espera `GET /` retornar JSON, mas o comportamento atual retorna o `index.html` (HTML). Esse teste está desatualizado e pode falhar — é seguro ignorá-lo ou atualizá-lo.

---

## Observações Importantes

**Dois bancos SQLite distintos**

O projeto usa dois SQLite com finalidades diferentes que **não devem ser confundidos:**
- `data/conversations.db` — histórico de chat por sessão (opcional, controlado por `USE_SQLITE`)
- `data/db/saved_notifications.db` — feedback (like/dislike) das notificações geradas (sempre inicializado)

**RAG sempre depende do Google**

Mesmo usando Ollama como provider LLM, o módulo RAG usa embeddings do Google (`gemini-embedding-001`). A `GEMINI_API_KEY` é obrigatória para qualquer funcionalidade que envolva RAG.

**Frontends são páginas independentes**

As 3 páginas não compartilham estado JavaScript entre si. A configuração feita no modal do `index.html` não é transmitida automaticamente para `notifications.html` ou `rag.html` — cada página gerencia seu próprio estado em memória.

**CORS liberado**

O `allow_origins=["*"]` está configurado para facilitar o desenvolvimento. Em produção, restrinja para as origens permitidas.

**Chave de API e segurança**

Nunca suba o arquivo `.env` para o repositório. Adicione-o ao `.gitignore`:

```bash
echo ".env" >> .gitignore
```