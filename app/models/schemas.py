"""
Schemas Pydantic para validação de requests e responses.

Define os modelos de dados usados na API.
"""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Request para o endpoint /chat."""
    
    session_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identificador único da sessão de conversa",
        examples=["user123", "sessao-teste-001"],
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Mensagem do usuário para o chatbot",
        examples=["Olá, tudo bem?", "Me explique o que é Python"],
    )
    
    model_override: str | None = Field(
        default=None,
        description="Nome do modelo específico para esta requisição (ex: gemini-3-pro-preview)",
    )


class PersonaOverride(BaseModel):
    """Override temporário para a persona."""
    
    description: str | None = Field(None, description="Nova descrição para a persona")
    system_prompt: str | None = Field(None, description="Novo system prompt")


class ProactiveChatRequest(BaseModel):
    """Request para o endpoint /chat/proactive."""
    
    persona_id: str = Field(
        ...,
        description="ID da persona a ser usada (tom do bot)",
        examples=["provocador", "motivador", "debochado"],
    )
    
    target_profile_id: str | None = Field(
        default=None,
        description="ID do perfil do usuário alvo (contexto)",
        examples=["gastao", "indiferente", "engajado"],
    )
    
    persona_override: PersonaOverride | None = Field(
        default=None,
        description="Override opcional das configurações da persona",
    )
    
    model_override: str | None = Field(
        default=None,
        description="Nome do modelo específico para esta requisição (ex: gemini-3-pro-preview)",
        examples=["gemini-1.5-pro", "gemini-1.5-flash"],
    )
    
    use_rag: bool | None = Field(
        default=None,
        description="Se o bot deve usar contexto da base de dados RAG (False para desativar)",
    )

    room_id: str | None = Field(
        default=None,
        description="ID do compartimento/sala usado para buscar medições e contexto real",
        examples=["2"],
    )

    sensor_external_id: str | None = Field(
        default=None,
        description="External ID do sensor usado para buscar a última medição real",
        examples=["SII-001"],
    )

    pessoa_id: str | None = Field(
        default=None,
        description="ID da pessoa para personalizar a notificação com dados reais do backend",
        examples=["ravilon"],
    )

    notification_type_id: str | None = Field(
        default=None,
        description="Subtipo de notificação (ex: reengajamento_streak, reengajamento_cofre)",
        examples=["reengajamento_streak", "reengajamento_cofre", "reengajamento_winback"],
    )
    notification_context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Variáveis dinâmicas do template do NotificationType. "
            "Ex.: {'streak_days': 14, 'hours_remaining': 3}"
        ),
        examples=[
            {"streak_days": 14, "hours_remaining": 3},
            {"coins_amount": 500, "expiry_deadline": "fim do mês", "redemption_example": "lâmpadas LED"},
        ],
    )


class RAGSearchRequest(BaseModel):
    """Request para teste direto do RAG /rag/search."""
    
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Termo ou pergunta a ser buscada na base vetorial",
    )
    k: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Número de chunks a retornar"
    )

class RAGSearchResult(BaseModel):
    """Unidade do resultado do RAG com Metadados."""
    content: str
    source: str
    page: int
    score: float

class RAGSearchResponse(BaseModel):
    """Response do /rag/search."""
    results: list[RAGSearchResult]
    query_echo: str


class PersonaResponse(BaseModel):
    """Modelo de persona para listagem."""
    
    id: str
    name: str
    description: str


class TargetProfileResponse(BaseModel):
    """Modelo de perfil de usuário alvo para listagem."""
    
    id: str
    name: str
    description: str


class ChatResponse(BaseModel):
    """Response do endpoint /chat."""
    
    session_id: str = Field(
        ...,
        description="Identificador da sessão (mesmo do request)",
    )
    reply: str = Field(
        ...,
        description="Resposta gerada pelo chatbot",
    )
    provider: Literal["ollama", "huggingface", "google"] = Field(
        ...,
        description="Provider LLM usado para gerar a resposta",
    )
    model: str = Field(
        ...,
        description="Nome do modelo usado para gerar a resposta",
    )
    context_summary: str | None = Field(
        default=None,
        description="Resumo do contexto operacional real usado para gerar a mensagem",
    )


class HealthResponse(BaseModel):
    """Response do endpoint /health."""
    
    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ...,
        description="Status geral da aplicação",
    )
    provider: str = Field(
        ...,
        description="Provider LLM configurado",
    )
    model: str = Field(
        ...,
        description="Modelo LLM configurado",
    )
    provider_available: bool = Field(
        ...,
        description="Se o provider está disponível e respondendo",
    )
    message: str | None = Field(
        default=None,
        description="Mensagem adicional (ex: erro de conexão)",
    )
    components: dict[str, str] | None = Field(
        default=None,
        description="Estado dos componentes externos (banco remoto, API Spring)",
    )


class RemoteDatabaseConnectionResponse(BaseModel):
    """Configuração e estado da conexão com o PostgreSQL remoto."""

    host: str
    port: int
    database: str
    user: str
    sslmode: str
    status: str | None = None
    database_name: str | None = None
    current_user: str | None = None


class RemoteDatabaseColumnResponse(BaseModel):
    """Metadados de uma coluna do banco remoto."""

    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool = False
    references: str | None = None


class RemoteDatabaseTableResponse(BaseModel):
    """Resumo de uma tabela do banco remoto."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema", serialization_alias="schema")
    table: str
    columns_count: int
    estimated_rows: int | None = None
    category: str
    relevance_score: int
    relevance_reason: str
    preview_endpoint: str


class RemoteDatabaseTableDetailResponse(RemoteDatabaseTableResponse):
    """Detalhe expandido de uma tabela remota."""

    columns: list[RemoteDatabaseColumnResponse]


class RemoteDatabaseCatalogResponse(BaseModel):
    """Catálogo explorável do PostgreSQL remoto."""

    connection: RemoteDatabaseConnectionResponse
    tables: list[RemoteDatabaseTableResponse]


class RemoteDatabaseRowsResponse(BaseModel):
    """Amostra paginada de linhas de uma tabela remota."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema", serialization_alias="schema")
    table: str
    limit: int
    offset: int
    row_count: int
    rows: list[dict[str, Any]]


class SpringEndpointResponse(BaseModel):
    """Metadados de um endpoint da API Spring remota."""

    id: str
    category: str
    method: str
    path_template: str
    description: str
    discovery_source: str
    relevance_score: int
    relevance_reason: str
    invoke_supported: bool = True
    side_effect: bool = False
    example_path_params: dict[str, str] = Field(default_factory=dict)
    example_query_params: dict[str, str] = Field(default_factory=dict)
    example_body: dict[str, Any] | list[Any] | None = None


class SpringApiCatalogResponse(BaseModel):
    """Catálogo explorável da API Spring Boot remota."""

    connection: dict[str, Any]
    endpoints: list[SpringEndpointResponse]


class ContextLookupOptionResponse(BaseModel):
    """Opção de autocomplete para sala, sensor ou pessoa."""

    id: str
    label: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpringEndpointInvokeRequest(BaseModel):
    """Payload para invocação proxy de um endpoint Spring catalogado."""

    path_params: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | list[Any] | None = None


class SpringEndpointInvokeResponse(BaseModel):
    """Resposta padronizada após invocar um endpoint remoto."""

    endpoint_id: str
    method: str
    path_template: str
    final_url: str
    status_code: int
    content_type: str
    data: Any


class IntegrationsRecommendationResponse(BaseModel):
    """Recursos externos priorizados para o projeto atual."""

    database_tables: list[RemoteDatabaseTableResponse]
    spring_endpoints: list[SpringEndpointResponse]


class IntegrationsCatalogResponse(BaseModel):
    """Visão consolidada das integrações externas disponíveis."""

    database: RemoteDatabaseCatalogResponse
    spring_api: SpringApiCatalogResponse
    recommendations: IntegrationsRecommendationResponse


class ErrorResponse(BaseModel):
    """Response padrão para erros."""
    
    error: str = Field(
        ...,
        description="Tipo do erro",
    )
    message: str = Field(
        ...,
        description="Mensagem descritiva do erro",
    )
    details: dict | None = Field(
        default=None,
        description="Detalhes adicionais do erro",
    )


class SavedNotificationCreate(BaseModel):
    """Payload recebido no POST /notifications/saved."""
    type: Literal["Pendente", "Aprovada", "Reprovada"] = "Pendente"
    content: str
    persona: str
    model: str
    target_profile: str | None = None
    prompt_used: str | None = None
    id: str | None = None
    date: str | None = None

class SavedNotificationResponse(BaseModel):
    """Payload retornado nas respostas."""
    id: str
    type: str
    content: str
    persona: str
    model: str
    date: str
    target_profile: str | None = None
    prompt_used: str | None = None

class NotificationTypeUpdate(BaseModel):
    type: Literal["Pendente", "Aprovada", "Reprovada"]
