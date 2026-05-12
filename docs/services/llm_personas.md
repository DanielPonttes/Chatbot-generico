# Servicos, LLM, Personas e Notificacoes

Esta documentacao cobre os componentes em `app/services/`.

## `llm_provider.py`

Define a interface `LLMProvider` e tres implementacoes:

- `GoogleGeminiProvider`
- `OllamaProvider`
- `HuggingFaceProvider`

### Factory

`get_llm_provider()` escolhe o provider a partir de `settings.llm_provider`.

Valores aceitos:

- `google`
- `ollama`
- `huggingface`

### Override de Modelo

Todos os providers aceitam `model_override` em `generate(...)`. O override vale apenas para aquela chamada e nao altera o provider global.

### Disponibilidade

`GET /health` chama `provider.is_available()` para reportar:

- `healthy`: provider disponivel;
- `degraded`: provider criado, mas sem resposta adequada;
- `unhealthy`: falha ao criar/verificar provider.

## `memory.py`

Gerencia historico de conversa.

Modos:

- RAM, padrao.
- SQLite, quando `USE_SQLITE=true`.

Configuracoes:

- `MEMORY_MAX_MESSAGES`
- `USE_SQLITE`
- `SQLITE_PATH`

## `persona_service.py`

Compoe o prompt final para notificacoes proativas.

### Personas

As personas definem tom de voz:

| ID | Nome | Intencao |
| --- | --- | --- |
| `provocador` | Provocador | Desafia o usuario com ironia leve. |
| `motivador` | Motivador | Incentiva com tom positivo. |
| `debochado` | Debochado | Usa sarcasmo leve sobre desperdicio. |

### Perfis-Alvo

Os perfis descrevem o receptor:

| ID | Nome | Contexto |
| --- | --- | --- |
| `gastao` | O Gastao Sem Nocao | Desperdica energia e nao se importa. |
| `indiferente` | O Indiferente | Ignora notificacoes e interage pouco. |
| `engajado` | O Engajado | Ja busca economia e interage com o app. |

### Tipos de Notificacao

Arquivo: `app/services/notification_type.yaml`

Cada entrada possui:

- `id`
- `name`
- `description`
- `default_use_rag`
- `required_context_vars`
- `system_prompt_template`

O YAML e carregado no import do modulo e validado com Pydantic. Erros de estrutura, IDs duplicados e variaveis obrigatorias ausentes no template quebram cedo no startup, em vez de falhar apenas durante uma requisicao.

Tipos atuais:

- `reengajamento_streak`
- `reengajamento_cofre`
- `reengajamento_winback`
- `social_ranking`
- `social_desafio_cooperativo`
- `conquista_badge`
- `conquista_impacto_ambiental`

### Variaveis Dinamicas

`notification_context` preenche o `system_prompt_template` com `str.format_map`.

Exemplo:

```json
{
  "notification_type_id": "reengajamento_streak",
  "notification_context": {
    "streak_days": 14,
    "hours_remaining": 3,
    "user_first_name": "Daniel"
  }
}
```

Variaveis em `required_context_vars` precisam estar presentes. Variaveis opcionais ausentes ficam como `{nome_da_variavel}` por causa do `_SafeDict`, evitando `KeyError`.

### Contexto Operacional

`generate_proactive_message(...)` tambem aceita:

- `room_id`
- `sensor_external_id`
- `pessoa_id`

Esses campos sao enviados ao `proactive_context.py`, que tenta buscar:

- sala no PostgreSQL remoto;
- sensor no PostgreSQL remoto;
- pessoa no PostgreSQL remoto e/ou Spring;
- ultima medicao por sala;
- ultima medicao por sensor.

### RAG

`use_rag` pode ser:

- `true`: forca RAG;
- `false`: desativa RAG;
- `null`: usa `default_use_rag` do tipo YAML; sem tipo, usa o comportamento legado `true`.

Quando ativo, o servico chama `get_relevant_context(...)` e injeta trechos da base vetorial no prompt.

### Retorno

O servico retorna `ProactiveMessageResult`:

- `message`: notificacao gerada;
- `context_summary`: resumo curto para UI;
- `prompt_used`: prompt completo salvo junto com a notificacao.

## `proactive_context.py`

Monta o contexto operacional real.

Saida:

- `summary`: texto curto para mostrar ao usuario.
- `prompt_block`: bloco usado no prompt do LLM.
- `metadata`: dados estruturados coletados.

Falhas de integracao sao tratadas de forma defensiva para que uma indisponibilidade parcial nao impeça sempre a geracao da notificacao.

## `integration_catalog.py`

Centraliza acesso exploratorio ao PostgreSQL remoto e ao catalogo da API Spring Boot.

Responsabilidades:

- testar conexao do PostgreSQL;
- listar tabelas relevantes;
- detalhar colunas e chaves;
- amostrar linhas;
- buscar salas, sensores e pessoas para autocomplete;
- listar endpoints Spring;
- invocar endpoints Spring suportados de forma controlada.

## Fluxo Completo de Notificacao

```text
POST /chat/proactive
  -> ProactiveChatRequest
  -> PersonaService.generate_proactive_message()
     -> persona
     -> target profile
     -> notification_type.yaml
     -> notification_context
     -> proactive_context.py
     -> RAG opcional
     -> LLM provider
  -> save_notification()
  -> ChatResponse
```

## Persistencia de Notificacoes

Arquivo: `app/api/db.py`

Tabela: `saved_notifications`

Campos:

- `id`
- `type`
- `content`
- `persona`
- `target_profile`
- `prompt_used`
- `model`
- `date`
- `created_at`

Tipos aceitos:

- `Pendente`
- `Aprovada`
- `Reprovada`
