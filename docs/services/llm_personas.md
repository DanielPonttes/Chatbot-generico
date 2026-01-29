# Serviços e Lógica de Negócio

Esta documentação cobre os componentes centrais de lógica da aplicação, localizados em `app/services/`.

## 1. Persona Service (`persona_service.py`)

Gerencia as personalidades do bot e os perfis de usuários alvo para a geração de mensagens proativas.

### Personas do Bot
Definem o "tom de voz" do chatbot. Atualmente configuradas:
1.  **Provocador**: Desafiador, irônico.
2.  **Motivador**: Positivo, encorajador.
3.  **Debochado**: Sarcástico, focado no desperdício.

### Perfis de Usuário Alvo (`TargetProfile`)
Definem o contexto de quem receberá a mensagem. Atualmente configurados:
1.  **O Gastão Sem Noção**: Desperdiça energia.
2.  **O Indiferente**: Ignora o app.
3.  **O Engajado**: Busca economia.

### Lógica de Geração (`generate_proactive_message`)
A função combina os seguintes elementos para criar o prompt final enviado ao LLM:
- **System Prompt da Persona**: Define como o bot se comporta.
- **Contexto do Target Profile**: Descreve o usuário alvo.
- **Instrução Base**: "Gere uma notificação curta..."

Fluxo:
`[Persona System Prompt] + [Target Profile Context] -> LLM -> Notificação`

## 2. LLM Provider (`llm_provider.py`)

Abstração para comunicação com modelos de linguagem.

### Estrutura
- **Classe Base Abstrata**: `LLMProvider`
- **Implementações**:
    - `GoogleGeminiProvider`: Usa SDK `google-generativeai`.
    - `OllamaProvider`: Usa API local Ollama.
    - `HuggingFaceProvider`: Usa API v2 do HuggingFace.

### Funcionalidade de Override
O método `generate` aceita um argumento opcional `model_override`.
- No **Gemini Provider**, isso instancia um novo objeto `genai.GenerativeModel` com o nome do modelo fornecido (ex: `gemini-3-flash-preview`) apenas para aquela requisição, sem alterar o estado global do serviço.

## 3. Gerenciador de Memória (`memory.py`)

Gerencia o histórico de conversas.
- Armazena mensagens em memória (dict) por `session_id`.
- Formata o histórico para o padrão esperado pelos providers (User/Assistant).
