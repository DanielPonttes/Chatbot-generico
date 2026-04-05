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
- **RAG opcional**: Injeta trechos de base de conhecimento quando `use_rag=true`.
- **Contexto operacional real**: Injeta sala, sensor, pessoa e últimas medições quando `room_id`, `sensor_external_id` e `pessoa_id` são informados.
- **Instrução Base**: "Gere uma notificação curta..."

Fluxo:
`[Persona] + [Target Profile] + [RAG opcional] + [Contexto operacional opcional] -> LLM -> Notificação`

O retorno inclui:

- `message`
- `context_summary`

## 2. Proactive Operational Context (`proactive_context.py`)

Responsável por montar o bloco de contexto operacional usado nas notificações.

### Fontes consultadas

- PostgreSQL remoto:
  - sala por `room_id`
  - sensor por `sensor_external_id`
  - pessoa por `pessoa_id`
- API Spring Boot:
  - pessoa
  - última medição por sala
  - última medição por sensor

### Saída produzida

- `summary`: resumo curto para exibição no frontend
- `prompt_block`: bloco textual incorporado ao prompt do LLM
- `metadata`: estrutura com os dados enriquecidos

## 3. LLM Provider (`llm_provider.py`)

Abstração para comunicação com modelos de linguagem.

### Estrutura
- **Classe Base Abstrata**: `LLMProvider`
- **Implementações**:
    - `GoogleGeminiProvider`: Usa SDK `google-genai`.
    - `OllamaProvider`: Usa API local Ollama.
    - `HuggingFaceProvider`: Usa API v2 do HuggingFace.

### Funcionalidade de Override
O método `generate` aceita um argumento opcional `model_override`.
- No **Gemini Provider**, a chamada usa o modelo override apenas naquela requisição, sem alterar o estado global do serviço.

## 4. Gerenciador de Memória (`memory.py`)

Gerencia o histórico de conversas.
- Armazena mensagens em memória (dict) por `session_id`.
- Formata o histórico para o padrão esperado pelos providers (User/Assistant).
