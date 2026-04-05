# Guia de Instalação e Execução

Este guia descreve como configurar o ambiente e executar o Chatbot Genérico.

## Pré-requisitos
- Python 3.11+
- `pip` e `venv`
- Node.js 18+
- `npm`
- Chave de API do Google Gemini, ou ambiente com Ollama, ou token HuggingFace

## Instalação

1. **Clone o repositório** (se aplicável)
2. **Crie e ative um ambiente virtual**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # ou
   .\venv\Scripts\activate   # Windows
   ```
3. **Instale as dependências**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Instale as dependências de E2E**:
   ```bash
   npm install
   npx playwright install chromium
   ```

## Configuração (.env)

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```ini
# Configurações Gerais
LOG_LEVEL=INFO

# Provider LLM (google, ollama, huggingface)
LLM_PROVIDER=google

# Google Gemini
GEMINI_API_KEY=sua_chave_api_aqui
GEMINI_MODEL=gemini-3-flash-preview

# Opcional: Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b

# Prompt de Sistema
BOT_SYSTEM_PROMPT="Você é um assistente útil e amigável."

# Integrações remotas do projeto
REMOTE_PG_HOST=srv1428963.hstgr.cloud
REMOTE_PG_PORT=5432
REMOTE_PG_USER=postgres
REMOTE_PG_PASSWORD=postgres
REMOTE_PG_DATABASE=procel_analytics
REMOTE_SPRING_BASE_URL=http://srv1428963.hstgr.cloud:8080
```

## Execução

Para iniciar o servidor de desenvolvimento com hot-reload:

```bash
uvicorn app.main:app --reload --port 8001
```

Acesse:
- **Chat Principal**: http://localhost:8001/
- **Teste de Notificações**: http://localhost:8001/notifications
- **Visualizador RAG**: http://localhost:8001/rag
- **Documentação Swagger (Auto-gerada)**: http://localhost:8001/docs

## Testes

### API

```bash
./venv/bin/pytest tests/test_api.py tests/test_integrations_api.py tests/test_proactive_context.py -q
```

### Interface com Playwright

```bash
npm run test:e2e
```

Em Linux/WSL, para instalar o Chromium com dependências do sistema:

```bash
sudo npx playwright install --with-deps chromium
```

## CI

O repositório possui workflow em `.github/workflows/ci.yml` com as jobs `Pytest` e `Playwright E2E`.

Detalhes adicionais:

- `docs/setup/ci.md`
- `scripts/apply_branch_protection.sh`

## Estrutura de Pastas

```
/
├── app/
│   ├── api/            # Rotas da API
│   ├── core/           # Configurações
│   ├── models/         # Schemas Pydantic
│   ├── services/       # Lógica de Negócio (LLM, Personas)
│   ├── static/         # Frontend (HTML, CSS, JS)
│   └── main.py         # Entry point
├── docs/               # Documentação do Projeto
├── tests/              # Testes automatizados
├── .github/            # Workflows de CI
├── package.json        # Setup do Playwright
├── .env                # Variáveis de ambiente
└── requirements.txt    # Dependências
```
