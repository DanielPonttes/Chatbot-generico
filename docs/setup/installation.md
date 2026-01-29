# Guia de Instalação e Execução

Este guia descreve como configurar o ambiente e executar o Chatbot Genérico.

## Pré-requisitos
- Python 3.10+
- `pip` e `venv`
- Chave de API do Google Gemini (para usar os modelos Gemini)

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

## Configuração (.env)

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```ini
# Configurações Gerais
LOG_LEVEL=INFO

# Provider LLM (google_gemini, ollama, huggingface)
LLM_PROVIDER=google_gemini

# Google Gemini
GEMINI_API_KEY=sua_chave_api_aqui
GEMINI_MODEL=gemini-2.0-flash

# Opcional: Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# Prompt de Sistema
BOT_SYSTEM_PROMPT="Você é um assistente útil e amigável."
```

## Execução

Para iniciar o servidor de desenvolvimento com hot-reload:

```bash
uvicorn app.main:app --reload --port 8001
```

Acesse:
- **Chat Principal**: http://localhost:8001/
- **Teste de Notificações**: http://localhost:8001/notifications
- **Documentação Swagger (Auto-gerada)**: http://localhost:8001/docs

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
├── tests/              # Scripts de teste
├── .env                # Variáveis de ambiente
└── requirements.txt    # Dependências
```
