# Plano de Implementação - Gemini 3.0 & Mensagens Proativas

Este plano descreve os passos para integrar o Google Gemini 3.0 como um provedor de LLM e implementar um sistema de mensagens proativas baseado em personas de usuários.

## Revisão do Usuário Necessária

> [!IMPORTANT]
> **Chave de API Necessária**: Você precisará fornecer uma `GEMINI_API_KEY` nas suas variáveis de ambiente ou no arquivo `.env`.
>
> **Gemini 3.0**: Usaremos `gemini-3-flash-preview` como modelo, conforme solicitado (anteriormente o padrão era 2.5).

## Alterações Propostas

### Configuração & Dependências

#### [MODIFY] [requirements.txt](file:///mnt/c/Users/ResTIC55/Chatbot-generico/requirements.txt)
- Adicionar biblioteca `google-generativeai`.

#### [MODIFY] [config.py](file:///mnt/c/Users/ResTIC55/Chatbot-generico/app/core/config.py)
- Adicionar configuração `GEMINI_API_KEY`.
- Adicionar configuração `gemini_model` (padrão: `gemini-3-flash-preview`).
- Adicionar `google` como uma opção válida para `llm_provider`.

### Serviços

#### [MODIFY] [llm_provider.py](file:///mnt/c/Users/ResTIC55/Chatbot-generico/app/services/llm_provider.py)
- Criar classe `GoogleGeminiProvider` implementando `LLMProvider`.
- Atualizar `get_llm_provider` para instanciar `GoogleGeminiProvider` quando `llm_provider` for "google".

#### [NEW] [persona_service.py](file:///mnt/c/Users/ResTIC55/Chatbot-generico/app/services/persona_service.py)
- Definir dataclass/modelo `Persona`.
- Implementar classe `PersonaService`:
    - `get_personas()`: Retorna lista de 3 personas fixas.
    - `generate_proactive_message(persona_id)`: Usa `LLMProvider` para gerar uma mensagem personalizada para a persona.

### Rotas da API

#### [MODIFY] [routes.py](file:///mnt/c/Users/ResTIC55/Chatbot-generico/app/api/routes.py)
- Adicionar endpoint `POST /chat/proactive`.
    - Aceita `persona_id`.
    - Retorna mensagem gerada.
- Adicionar endpoint `GET /personas`.
    - Retorna lista de personas disponíveis.

## Plano de Verificação

### Testes Automatizados
1.  **Testar integração Gemini**:
    -   Não executaremos testes automatizados contra a API ao vivo durante o build para evitar uso/vazamento de chaves, mas podemos verificar se o provider é instanciado corretamente.
2.  **Testar Endpoint Proativo**:
    -   Usar `curl` para chamar `POST /chat/proactive` com um provider mock ou o real (se a chave for fornecida).

### Verificação Manual
1.  **Configuração**:
    -   Adicionar `GEMINI_API_KEY=...` ao `.env`.
    -   Definir `LLM_PROVIDER=google`.
2.  **Executar API**:
    -   Iniciar servidor: `uvicorn app.main:app --reload`.
3.  **Testar Funcionalidades**:
    -   **Health Check**: Acessar `GET /health` para verificar se o provider "google" está ativo.
    -   **Listar Personas**: Acessar `GET /personas` para ver as 3 opções.
    -   **Disparar Mensagem**: Acessar `POST /chat/proactive` com diferentes `persona_id` e verificar se o conteúdo da mensagem corresponde à persona.
