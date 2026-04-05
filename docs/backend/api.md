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

### 6. Catálogo de Integrações Externas
Consolida os recursos do PostgreSQL remoto (`procel_analytics`) e da API Spring Boot hospedada em `srv1428963.hstgr.cloud:8080`.

- **Método**: `GET`
- **Rota**: `/integrations/catalog`
- **Resposta**:
    - Metadados de conexão do PostgreSQL remoto
    - Lista priorizada de tabelas relevantes (`medicao`, `sensor`, `compartimento`, `presenca`, `pessoa`, `parametro_*`)
    - Catálogo dos endpoints Spring observados/confirmados
    - Recomendações dos recursos mais relevantes para o projeto

### 7. Explorar Tabelas do PostgreSQL Remoto

- **Método**: `GET`
- **Rota**: `/integrations/database/tables`
- **Rota de detalhe**: `/integrations/database/tables/{schema}/{table}`
- **Rota de amostra**: `/integrations/database/tables/{schema}/{table}/rows?limit=25&offset=0`

Essas rotas permitem listar tabelas, inspecionar colunas/chaves e amostrar registros diretamente do banco remoto sem escrever SQL no frontend.

### 8. Catálogo da API Spring Boot

- **Método**: `GET`
- **Rota**: `/integrations/spring/endpoints`
- **Invocação proxy**: `POST /integrations/spring/endpoints/{endpoint_id}/invoke`

Endpoints confirmados como úteis no ambiente atual:

- `POST /api/rooms/sync`
- `POST /api/pessoas`
- `GET /api/pessoas/{pessoa_id}`
- `PUT /api/pessoas/{pessoa_id}`
- `POST /api/presencas/checkin`
- `POST /api/presencas/checkout`
- `POST /api/sensors/ingest/mock`
- `GET /api/sensors/{sensor_external_id}/medicoes`
- `GET /api/sensors/{sensor_external_id}/medicoes/latest`
- `GET /api/rooms/{room_id}/medicoes`
- `GET /api/rooms/{room_id}/medicoes/latest`

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
- `room_id` (str, opcional): ID do compartimento/sala para buscar o contexto real.
- `sensor_external_id` (str, opcional): External ID do sensor para buscar a última medição.
- `pessoa_id` (str, opcional): ID da pessoa para enriquecer a notificação com dados reais do backend.

### PersonaOverride
- `description` (str, opcional)
- `system_prompt` (str, opcional)
