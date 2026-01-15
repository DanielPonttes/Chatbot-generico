# 🤖 Chatbot Genérico

> Um chatbot simples e **gratuito** para projetos de faculdade, com suporte a modelos LLM locais via Ollama ou HuggingFace Inference API.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 📋 Índice

- [Visão Geral](#-visão-geral)
- [Requisitos](#-requisitos)
- [Instalação](#-instalação)
- [Configuração](#-configuração)
- [Como Executar](#-como-executar)
- [Interface Web (Frontend)](#-interface-web-frontend)
- [Exemplos de Uso](#-exemplos-de-uso)
- [Estrutura de Pastas](#-estrutura-de-pastas)
- [API Reference](#-api-reference)
- [Testes](#-testes)
- [Limitações](#-limitações)
- [Próximos Passos](#-próximos-passos)

## 🎯 Visão Geral

Este projeto implementa um chatbot de perguntas e respostas em português brasileiro, com:

- **Memória de conversa**: Mantém contexto das últimas 10 mensagens por sessão
- **Persona configurável**: Customize o comportamento do bot via variável de ambiente
- **Múltiplos providers**: Ollama (local, gratuito) ou HuggingFace (API, gratuito com limites)
- **API HTTP**: Pronto para integrar com qualquer frontend
- **Custo zero**: Projetado para rodar em notebooks comuns sem custos

### Por que Qwen 2.5 0.5B como modelo padrão?

| Modelo | Parâmetros | Tamanho | Qualidade PT-BR | Velocidade |
|--------|-----------|---------|-----------------|------------|
| **qwen2.5:0.5b** ⭐ | 500M | ~400MB | Boa | Muito rápido |
| qwen2.5:1.5b | 1.5B | ~1GB | Muito boa | Rápido |
| llama3.2:1b | 1B | ~700MB | Boa | Rápido |
| phi3:mini | 3.8B | ~2GB | Excelente | Moderado |

O **Qwen 2.5 0.5B** foi escolhido como padrão por ser o menor modelo que ainda entrega respostas aceitáveis em português, ideal para notebooks com recursos limitados.

## 📦 Requisitos

- **Python 3.11+**
- **Ollama** (recomendado) ou **HuggingFace Token**
- ~1GB de espaço em disco (para o modelo)
- 4GB+ de RAM recomendado

## 🚀 Instalação

### 1. Clone o repositório

```bash
git clone <url-do-repositorio>
cd chatbot-generico
```

### 2. Crie um ambiente virtual

```bash
# Criar venv
python3 -m venv venv

# Ativar (Linux/Mac)
source venv/bin/activate

# Ativar (Windows)
.\venv\Scripts\activate
```

### 3. Instale as dependências

**Opção A: pip (mais simples)**
```bash
pip install -r requirements.txt
```

**Opção B: pip com extras de desenvolvimento**
```bash
pip install -e ".[dev]"
```

### 4. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env conforme necessário
```

## ⚙️ Configuração

### Usando Ollama (Recomendado) 🏠

O Ollama permite executar modelos LLM localmente, sem custo e sem internet.

#### Passo 1: Instale o Ollama

```bash
# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Mac
brew install ollama

# Windows
# Baixe o instalador em: https://ollama.ai/download
```

#### Passo 2: Inicie o servidor Ollama

```bash
ollama serve
```

#### Passo 3: Baixe o modelo

```bash
# Modelo padrão (recomendado, ~400MB)
ollama pull qwen2.5:0.5b

# Alternativas (melhor qualidade, mais pesados):
# ollama pull qwen2.5:1.5b   # ~1GB
# ollama pull llama3.2:1b    # ~700MB
# ollama pull phi3:mini      # ~2GB
# ollama pull deepseek-r1:latest # ~5GB
```

#### Passo 4: Configure o .env

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b
```

### Usando HuggingFace (Alternativa) 🌐

Se não puder instalar Ollama, use a API do HuggingFace como fallback.

#### Passo 1: Obtenha um token

1. Acesse [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Clique em "New token"
3. Dê um nome e copie o token

#### Passo 2: Configure o .env

```env
LLM_PROVIDER=huggingface
HF_TOKEN=
HF_MODEL=microsoft/DialoGPT-small
```

> ⚠️ **Atenção**: A camada gratuita do HuggingFace tem limites de requisições. Para uso intensivo, prefira Ollama.

### Variáveis de Ambiente Disponíveis

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `LLM_PROVIDER` | Provider a usar: `ollama` ou `huggingface` | `ollama` |
| `OLLAMA_BASE_URL` | URL do servidor Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modelo Ollama | `qwen2.5:0.5b` |
| `HF_TOKEN` | Token HuggingFace | - |
| `HF_MODEL` | Modelo HuggingFace | `microsoft/DialoGPT-small` |
| `BOT_SYSTEM_PROMPT` | Persona do bot | Assistente amigável PT-BR |
| `MEMORY_MAX_MESSAGES` | Mensagens no histórico | `10` |
| `USE_SQLITE` | Persistir conversas em SQLite | `false` |
| `DEBUG` | Ativar logs detalhados | `false` |

## ▶️ Como Executar

### Iniciar o servidor

```bash
# Com uvicorn (recomendado)
uvicorn app.main:app --reload

# Ou diretamente
python -m app.main
```

O servidor iniciará em `http://localhost:8000`.

### Verificar se está funcionando

Acesse no navegador:
- **Interface de Testes**: http://localhost:8000
- **Documentação interativa**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

## 🖥️ Interface Web (Frontend)

O projeto inclui uma interface web de testes integrada, acessível em `http://localhost:8000` quando o servidor está rodando.

### Recursos

- **Design moderno escuro** com animações suaves
- **Indicador de status** do modelo LLM em tempo real
- **Histórico de mensagens** por sessão
- **Botões de ação rápida** para testar prompts comuns
- **Gerenciamento de sessão** (nova sessão, limpar chat)

### Como usar

1. Inicie o servidor:
   ```bash
   uvicorn app.main:app --reload
   ```

2. Acesse no navegador: **http://localhost:8000**

3. Digite sua mensagem e pressione Enter ou clique no botão de enviar

> **Dica**: Use os botões de ação rápida para testar diferentes tipos de perguntas.

## 💬 Exemplos de Uso

### Health Check

```bash
curl http://localhost:8000/health
```

Resposta:
```json
{
  "status": "healthy",
  "provider": "ollama",
  "model": "qwen2.5:0.5b",
  "provider_available": true,
  "message": null
}
```

### Enviar Mensagem

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "usuario-123",
    "message": "Olá, tudo bem?"
  }'
```

Resposta:
```json
{
  "session_id": "usuario-123",
  "reply": "Olá! Tudo bem sim, obrigado por perguntar! Como posso ajudar você hoje?",
  "provider": "ollama",
  "model": "qwen2.5:0.5b"
}
```

### Continuar Conversa (mesmo session_id)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "usuario-123",
    "message": "Me explique o que é Python"
  }'
```

O bot lembrará da conversa anterior porque usamos o mesmo `session_id`.

### Trocar Persona

No arquivo `.env`:
```env
BOT_SYSTEM_PROMPT=Você é um professor de programação paciente e didático. Explique conceitos de forma simples, com exemplos práticos.
```

## 📁 Estrutura de Pastas

```
chatbot-generico/
├── app/                           # Código da aplicação
│   ├── __init__.py
│   ├── main.py                    # Entry point FastAPI
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py              # Configurações (Pydantic Settings)
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py             # Schemas request/response
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_provider.py        # Providers LLM (Ollama, HuggingFace)
│   │   └── memory.py              # Gerenciador de memória
│   └── api/
│       ├── __init__.py
│       └── routes.py              # Endpoints /chat, /health
├── tests/                         # Testes automatizados
│   ├── __init__.py
│   ├── conftest.py                # Fixtures pytest
│   └── test_api.py                # Testes dos endpoints
├── .env.example                   # Template de configuração
├── pyproject.toml                 # Dependências (Poetry/setuptools)
├── requirements.txt               # Dependências (pip)
└── README.md                      # Este arquivo
```

## 📚 API Reference

### POST /chat

Envia uma mensagem e recebe a resposta do chatbot.

**Request Body:**
```json
{
  "session_id": "string (1-100 chars)",
  "message": "string (1-4000 chars)"
}
```

**Response:**
```json
{
  "session_id": "string",
  "reply": "string",
  "provider": "ollama | huggingface",
  "model": "string"
}
```

**Códigos de Status:**
- `200`: Sucesso
- `422`: Erro de validação
- `503`: Provider não disponível

### GET /health

Verifica o status da aplicação.

**Response:**
```json
{
  "status": "healthy | degraded | unhealthy",
  "provider": "string",
  "model": "string",
  "provider_available": true | false,
  "message": "string | null"
}
```

### GET /docs

Documentação interativa (Swagger UI).

### GET /redoc

Documentação alternativa (ReDoc).

## 🧪 Testes

Execute os testes com pytest:

```bash
# Rodar todos os testes
pytest

# Com output verboso
pytest -v

# Com cobertura
pytest --cov=app
```

Os testes usam mocks para não depender de Ollama/HuggingFace rodando.

## ⚠️ Limitações

1. **Modelo pequeno**: O Qwen 0.5B é limitado em raciocínio complexo e pode dar respostas genéricas
2. **Sem RAG**: Não há integração com documentos externos
3. **Memória simples**: O histórico é apenas concatenado, sem sumarização
4. **Sem autenticação**: A API é aberta (adicione auth para produção)
5. **Single-tenant**: Não há isolamento entre usuários
6. **CPU-only**: Modelos rodam em CPU (GPU acelera significativamente)

## 🚀 Próximos Passos

Sugestões para evoluir o projeto:

1. **Frontend**: Criar interface web com React ou Vue
2. **Autenticação**: Adicionar JWT ou API keys
3. **RAG**: Integrar com documentos usando embeddings
4. **Modelo maior**: Usar phi3:mini ou llama3.2:3b para melhor qualidade
5. **Cache**: Adicionar Redis para respostas frequentes
6. **Logs estruturados**: Usar Loguru ou structlog
7. **Docker**: Containerizar a aplicação
8. **GPU**: Configurar CUDA/Metal para aceleração

## 📄 Licença

MIT License - use livremente para seu projeto de faculdade! 🎓

---

**Desenvolvido para fins educacionais** 📚

Se tiver dúvidas, abra uma issue ou consulte a documentação em `/docs`.
