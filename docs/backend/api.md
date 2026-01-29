# Documentação da API Backend

Esta seção detalha os endpoints, modelos de dados e estrutura do backend da aplicação Chatbot Genérico.

## Estrutura Geral
O backend é construído em **Python** utilizando **FastAPI**.

- **Entrada Principal**: `app/main.py`
- **Rotas**: `app/api/routes.py`
- **Modelos Pydantic**: `app/models/schemas.py`
- **Serviços**: `app/services/`

## Endpoints

### 1. Health Check
Verifica a saúde do serviço e o status do provedor LLM.

- **Método**: `GET`
- **Rota**: `/health`
- **Resposta**:
    ```json
    {
      "status": "ok",
      "provider": "google_gemini",
      "model": "gemini-2.0-flash",
      "provider_available": true
    }
    ```

### 2. Chat Interativo
Envia mensagens para o bot e recebe respostas. Suporta histórico de sessão e override de modelo.

- **Método**: `POST`
- **Rota**: `/chat`
- **Corpo da Requisição (`ChatRequest`)**:
    ```json
    {
      "session_id": "string",
      "message": "string",
      "model_override": "gemini-3-flash-preview" // Opcional
    }
    ```
- **Resposta (`ChatResponse`)**:
    ```json
    {
      "session_id": "string",
      "reply": "string",
      "provider": "string",
      "model": "string"
    }
    ```

### 3. Chat Proativo (Notificação)
Gera uma mensagem inicial baseada em uma persona e perfil de usuário alvo.

- **Método**: `POST`
- **Rota**: `/chat/proactive`
- **Corpo da Requisição (`ProactiveChatRequest`)**:
    ```json
    {
      "persona_id": "debochado",
      "target_profile_id": "gastao", // Opcional
      "model_override": "gemini-3-pro-preview", // Opcional
      "persona_override": { // Opcional
        "system_prompt": "string"
      }
    }
    ```
- **Resposta**: Mesmo formato de `ChatResponse`.

### 4. Listar Personas
Retorna as personas disponíveis para o bot.

- **Método**: `GET`
- **Rota**: `/personas`
- **Resposta**: Lista de objetos `PersonaResponse`.

### 5. Listar Perfis de Usuário
Retorna os perfis de usuários alvo disponíveis.

- **Método**: `GET`
- **Rota**: `/target-profiles`
- **Resposta**: Lista de objetos `TargetProfileResponse`.

## Modelos de Dados (Schemas)

### ChatRequest
- `session_id` (str): Identificador único da sessão.
- `message` (str): Mensagem do usuário.
- `model_override` (str, opcional): Nome do modelo a ser usado especificamente nesta requisição.

### ProactiveChatRequest
- `persona_id` (str): ID da persona do bot (Ex: "provocador").
- `target_profile_id` (str, opcional): ID do perfil do usuário alvo (Ex: "gastao").
- `model_override` (str, opcional): Nome do modelo LLM.
- `persona_override` (PersonaOverride, opcional): Permite definir um System Prompt customizado temporário.

### PersonaOverride
- `description` (str, opcional)
- `system_prompt` (str, opcional)
