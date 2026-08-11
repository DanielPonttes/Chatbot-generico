"""
Schemas Pydantic para validação de requests e responses.

Define os modelos de dados usados na API.
"""

import json
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


MODEL_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$"
NOTIFICATION_CONTEXT_MAX_BYTES = 8_192
NotificationStatus = Literal["Pendente", "Aprovada", "Reprovada"]


NOTIFICATION_CONTEXT_GROUPS = {
    "user_and_rewards": [
        "user_first_name",
        "user_name",
        "gamification_profile",
        "xp_reward",
        "coins_reward",
        "coin_balance",
        "current_xp",
    ],
    "mission_and_progress": [
        "mission_name",
        "target_action",
        "target_time_window",
        "mission_progress_percent",
        "remaining_action",
        "deadline",
        "current_progress_percent",
    ],
    "location_and_identity": [
        "room_id",
        "corridor_id",
        "floor_id",
        "course_id",
        "sensor_external_id",
        "pessoa_id",
    ],
    "indoor_telemetry": [
        "presence_status",
        "luminosity_level",
        "lux_level",
        "current_lux_reading",
        "temperature_internal",
        "ruido_ambiente",
        "ac_status",
        "status_iluminacao",
        "door_window_sensor_status",
        "measured_consumption_kwh",
        "measured_hourly_consumption",
        "consumo_circuito",
        "lighting_power_delta",
        "cooling_consumption_kwh",
    ],
    "external_context_and_baselines": [
        "external_temperature",
        "temperature_external",
        "external_humidity",
        "humidity_external",
        "weather_condition",
        "historical_baseline_kwh",
        "room_baseline_consumption",
        "building_baseline_kwh",
        "historical_peak_kwh",
        "recommended_temperature_range",
        "target_lux_range",
    ],
    "ranking_and_achievements": [
        "positions_gained",
        "current_rank_percentile",
        "current_rank_position",
        "weekly_efficiency_index",
        "efficiency_index_trend",
        "badge_name",
        "badge_description",
        "trigger_action",
        "kwh_saved",
        "impact_metric_value",
        "impact_metric_unit",
    ],
}


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
        max_length=100,
        pattern=MODEL_NAME_PATTERN,
        description="Nome do modelo específico, se habilitado pela allowlist do ambiente",
    )


class PersonaOverride(BaseModel):
    """Override temporário para a persona."""
    
    description: str | None = Field(None, max_length=1000, description="Nova descrição para a persona")
    system_prompt: str | None = Field(None, max_length=4000, description="Novo system prompt")


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
        max_length=100,
        pattern=MODEL_NAME_PATTERN,
        description="Nome do modelo específico, se habilitado pela allowlist do ambiente",
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
        max_length=32,
        description=(
            "Objeto extensível com as variáveis dinâmicas do template escolhido. "
            "Consulte GET /v1/notifications/types para descobrir as variáveis "
            "obrigatórias do notification_type_id. O documento de missões também "
            "define contexto de usuário, recompensas, sala, sensores, consumo, "
            "clima, rankings e conquistas."
        ),
        examples=[
            {"streak_days": 14, "hours_remaining": 3},
            {"coins_amount": 500, "expiry_deadline": "fim do mês", "redemption_example": "lâmpadas LED"},
            {
                "room_id": "sala-204",
                "user_first_name": "Daniel",
                "target_action": "reduzir o consumo entre 18h e 21h",
                "target_time_window": "hoje, das 18h às 21h",
                "reward_description": "100 EcoCoins",
                "xp_reward": 50,
                "coins_reward": 100,
            },
            {
                "room_id": "sala-204",
                "anomaly_window": "últimas 2 horas",
                "measured_consumption_kwh": 8.4,
                "expected_consumption_kwh": 5.2,
                "anomaly_percent": 61.5,
                "potential_wasted_kwh": 3.2,
                "recommended_action": "verificar a iluminação e o ar-condicionado",
            },
        ],
        json_schema_extra={
            "additionalProperties": True,
            "x-procel-context-groups": NOTIFICATION_CONTEXT_GROUPS,
        },
    )

    @field_validator("notification_context")
    @classmethod
    def validate_notification_context_size(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Limita chaves e tamanho serializado do contexto dinâmico."""
        if value is None:
            return None

        try:
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("notification_context deve conter apenas valores JSON") from exc
        if len(value) > 32 or len(serialized.encode("utf-8")) > NOTIFICATION_CONTEXT_MAX_BYTES:
            raise ValueError(
                "notification_context deve ter no máximo 32 chaves e 8 KiB serializados"
            )
        return value


class NotificationGenerateRequest(ProactiveChatRequest):
    """Request dedicado à geração por uma missão do catálogo V3."""

    mission_id: str = Field(
        ...,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
        description=(
            "ID estável retornado por GET /v1/notifications/missions. "
            "O backend resolve o template técnico associado e valida suas variáveis."
        ),
        examples=["ultimo_a_apagar", "sala_vazia_luz_off"],
    )
    use_canonical_context: bool = Field(
        default=False,
        description=(
            "Quando true, resolve pessoa_id, room_id e sensor_external_id pelos "
            "contratos canônicos antes da geração. Exige chave administrativa, "
            "TLS na origem e snapshots fresh. Valores enviados que divirjam da "
            "fonte são rejeitados."
        ),
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


class NotificationTypeResponse(BaseModel):
    """Catálogo público dos templates de notificação executáveis."""

    id: str = Field(
        ...,
        description="ID técnico usado em notification_type_id.",
        examples=["missao_convite", "feedback_alerta_consumo"],
    )
    name: str = Field(..., description="Nome legível do template.")
    category: str = Field(
        ...,
        description=(
            "Categoria do documento de notificações: Conquistas e Progresso, "
            "Desafios e Missões, Feedback em Tempo Real, Social e Competição "
            "ou Reengajamento."
        ),
    )
    subtype: str = Field(
        ...,
        description="Subtipo funcional usado para escolher o template.",
    )
    description: str = Field(..., description="Objetivo e caso de uso do template.")
    default_use_rag: bool = Field(
        ...,
        description="Indica se o RAG é usado por padrão quando use_rag não é enviado.",
    )
    required_context_vars: list[str] = Field(
        ...,
        description="Chaves que devem existir em notification_context para gerar a mensagem.",
        examples=[["anomaly_window", "measured_consumption_kwh", "expected_consumption_kwh"]],
    )
    context_variables: list[str] = Field(
        ...,
        description=(
            "Todas as variáveis aceitas pelo prompt do template, incluindo as "
            "opcionais. A lista é a fonte de descoberta para integrações."
        ),
    )


class NotificationMissionResponse(BaseModel):
    """Missão de produto normalizada a partir do documento V3."""

    mission_id: str = Field(
        ...,
        description="Identificador estável usado para referenciar a missão.",
        examples=["ultimo_a_apagar", "sala_vazia_luz_off"],
    )
    name: str = Field(..., description="Nome da missão no documento de produto.")
    category: str = Field(..., description="Categoria funcional da missão.")
    subtype: str = Field(..., description="Subtipo de notificação associado.")
    template_id: str | None = Field(
        default=None,
        description=(
            "ID do template técnico atual quando há mapeamento exato. Nulo indica "
            "que a missão está catalogada, mas ainda não possui geração executável."
        ),
    )
    execution_status: Literal["mapped_template", "catalog_only"] = Field(
        ...,
        description="Estado da implementação da missão no agente.",
    )
    example: str = Field(..., description="Exemplo de mensagem registrado na matriz V3.")
    component_inputs: list[str] = Field(
        ...,
        description="Variáveis fornecidas por outros componentes, sensores ou integrações.",
    )
    agent_inputs: list[str] = Field(
        ...,
        description="Variáveis que o agente precisa derivar ou receber do contexto de geração.",
    )
    context_variables: list[str] = Field(
        ...,
        description="União ordenada das variáveis de entrada da missão.",
    )
    template_required_context_vars: list[str] = Field(
        default_factory=list,
        description=(
            "Variáveis obrigatórias do template técnico associado. Pode ser mais "
            "ampla que a lista de entradas da missão até que o contrato dos outros "
            "componentes seja fechado."
        ),
    )


class NotificationMissionCatalogResponse(BaseModel):
    """Envelope versionado do catálogo de missões."""

    catalog_version: str = Field(..., description="Versão do catálogo normalizado.")
    source_document: str = Field(..., description="Documento de origem da matriz.")
    mission_count: int = Field(..., ge=0, description="Quantidade de missões no catálogo.")
    missions: list[NotificationMissionResponse]


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


class NodeGpuMetrics(BaseModel):
    """Telemetria não sensível de uma GPU do host."""

    index: int = Field(..., ge=0)
    name: str = Field(..., min_length=1, max_length=200)
    utilization_percent: float | None = Field(default=None, ge=0, le=100)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    memory_total_bytes: int | None = Field(default=None, ge=0)
    temperature_c: float | None = Field(default=None, ge=0)
    power_w: float | None = Field(default=None, ge=0)


class NodeMetricsResponse(BaseModel):
    """Snapshot validado produzido pelo agente local do host."""

    schema_version: int = Field(..., ge=1)
    collected_at: datetime = Field(..., description="Instante UTC da coleta")
    age_seconds: float = Field(..., ge=0, description="Idade do snapshot")
    fresh: bool = Field(..., description="Se o snapshot está dentro do TTL configurado")
    clock_skew: bool = Field(
        default=False,
        description="Indica timestamp no futuro em relação ao backend",
    )
    hostname: str = Field(..., min_length=1, max_length=255)
    host_uptime_seconds: float | None = Field(default=None, ge=0)
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    memory_total_bytes: int | None = Field(default=None, ge=0)
    memory_available_bytes: int | None = Field(default=None, ge=0)
    memory_used_percent: float | None = Field(default=None, ge=0, le=100)
    disk_path: str = Field(..., min_length=1, max_length=64)
    disk_total_bytes: int = Field(..., ge=0)
    disk_used_bytes: int = Field(..., ge=0)
    disk_used_percent: float | None = Field(default=None, ge=0, le=100)
    gpu_available: bool
    gpus: list[NodeGpuMetrics] = Field(default_factory=list)
    services: dict[str, str] = Field(default_factory=dict)


class AdminStatusResponse(BaseModel):
    """Readiness detalhado protegido para o futuro painel administrativo."""

    service: str = Field(..., description="Nome da aplicação monitorada")
    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ...,
        description="Status geral do runtime",
    )
    provider: str = Field(..., description="Provider LLM configurado")
    model: str = Field(..., description="Modelo LLM configurado")
    provider_available: bool = Field(
        ...,
        description="Se o provider LLM respondeu ao health check",
    )
    components: dict[str, str] = Field(
        default_factory=dict,
        description="Estado resumido das integrações externas",
    )
    checked_at: datetime = Field(..., description="Instante UTC da verificação")
    uptime_seconds: float = Field(
        ...,
        ge=0,
        description="Tempo de processo desde o último startup",
    )
    node_metrics: NodeMetricsResponse | None = Field(
        default=None,
        description="Snapshot local do host; ausente até o agente publicar um arquivo válido",
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


ContextStatus = Literal["fresh", "stale", "empty"]


class ContextMetadata(BaseModel):
    """Metadados de origem e freshness de um snapshot canônico."""

    source: str
    scope: str
    status: ContextStatus
    fresh: bool
    observed_at: datetime | None = None
    fetched_at: datetime
    age_seconds: float | None = None
    max_age_seconds: int
    clock_skew: bool = False


class CanonicalUserProfileData(BaseModel):
    """Perfil mínimo; não inclui e-mail, telefone, matrícula ou senha."""

    user_id: str
    display_name: str | None = None


class CanonicalUserProfileResponse(BaseModel):
    metadata: ContextMetadata
    data: CanonicalUserProfileData | None


class CanonicalActivityItem(BaseModel):
    """Atividade observada associada a uma missão."""

    activity_id: str
    mission_id: str
    status: str
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    mission_type: str | None = None
    mission_title: str | None = None
    mission_value: int | None = None


class CanonicalActivitiesData(BaseModel):
    user_id: str
    items: list[CanonicalActivityItem]
    total: int
    by_status: dict[str, int]
    latest_event_at: datetime | None = None
    limit: int


class CanonicalActivitiesResponse(BaseModel):
    metadata: ContextMetadata
    data: CanonicalActivitiesData


class CanonicalTelemetryMetric(BaseModel):
    name: str
    value: Any
    unit: str | None = None


class CanonicalTelemetryData(BaseModel):
    measurement_id: str
    target_id: str
    sensor_external_id: str | None = None
    room_id: str | None = None
    source: str
    observed_at: datetime
    metrics: list[CanonicalTelemetryMetric]


class CanonicalTelemetryResponse(BaseModel):
    metadata: ContextMetadata
    data: CanonicalTelemetryData | None


class CanonicalPresenceData(BaseModel):
    room_id: str
    room_name: str | None = None
    occupied_count: int
    capacity: int | None = None
    occupancy_pct: float | None = None
    records_count: int
    latest_open_checkin_at: datetime | None = None
    latest_event_at: datetime | None = None
    as_of: datetime


class CanonicalPresenceResponse(BaseModel):
    metadata: ContextMetadata
    data: CanonicalPresenceData


class CanonicalMissionItem(BaseModel):
    mission_id: str
    type: str
    title: str
    description: str | None = None
    value: int
    active: bool
    parent_id: str | None = None
    created_at: datetime


class CanonicalMissionsData(BaseModel):
    active_only: bool
    items: list[CanonicalMissionItem]
    total: int
    limit: int


class CanonicalMissionsResponse(BaseModel):
    metadata: ContextMetadata
    data: CanonicalMissionsData


class CanonicalParameterDefinitionItem(BaseModel):
    parameter_id: str
    data_type: str
    unit: str | None = None
    sensor_type: str
    name: str
    description: str | None = None
    active: bool


class CanonicalParameterDefinitionsData(BaseModel):
    active_only: bool
    items: list[CanonicalParameterDefinitionItem]
    total: int
    limit: int


class CanonicalParameterDefinitionsResponse(BaseModel):
    metadata: ContextMetadata
    data: CanonicalParameterDefinitionsData


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
    # A criação pública sempre começa pendente; revisão ocorre via PATCH admin.
    type: Literal["Pendente"] = Field(
        default="Pendente",
        description="Novas notificações entram sempre como candidatas pendentes.",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Texto final da notificação candidata.",
        examples=["⚡ Você reduziu o consumo da sala em 12% hoje!"],
    )
    persona: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="ID da persona que definiu o tom da mensagem.",
        examples=["motivador"],
    )
    model: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=MODEL_NAME_PATTERN,
        description="Modelo usado para gerar a mensagem.",
        examples=["gemma4:26b"],
    )
    target_profile: str | None = Field(
        default=None,
        max_length=100,
        description="ID opcional do perfil de usuário usado no contexto.",
        examples=["engajado"],
    )
    prompt_used: str | None = Field(
        default=None,
        max_length=8000,
        description="Prompt técnico usado na geração; opcional para salvamento manual.",
    )
    id: str | None = Field(
        default=None,
        description="ID idempotente opcional; se omitido, o backend gera um UUID.",
    )
    date: str | None = Field(
        default=None,
        description="Data/hora da notificação; se omitida, o backend preenche.",
        examples=["2026-08-10T12:00:00+00:00"],
    )

class SavedNotificationResponse(BaseModel):
    """Payload retornado nas respostas."""
    id: str = Field(..., description="Identificador único da notificação salva.")
    type: NotificationStatus = Field(..., description="Estado da revisão humana.")
    content: str = Field(..., description="Texto final da notificação.")
    persona: str = Field(..., description="Persona usada na geração.")
    model: str = Field(..., description="Modelo usado na geração.")
    date: str = Field(..., description="Data/hora registrada para a notificação.")
    target_profile: str | None = Field(
        default=None,
        description="Perfil de usuário alvo, quando informado.",
    )
    prompt_used: str | None = Field(
        default=None,
        description="Prompt usado na geração; pode ser omitido em integrações futuras.",
    )


class SavedNotificationCreateResponse(BaseModel):
    """Confirmação da criação de uma notificação candidata."""

    status: Literal["success"] = Field(..., description="Indica que o registro foi salvo.")


class NotificationReviewResponse(BaseModel):
    """Confirmação da avaliação administrativa de uma notificação."""

    status: Literal["success"] = Field(..., description="Indica que a avaliação foi aplicada.")
    id: str = Field(..., description="ID da notificação avaliada.")
    type: NotificationStatus = Field(..., description="Novo estado da notificação.")


class SavedNotificationDeleteResponse(BaseModel):
    """Confirmação da remoção de uma notificação."""

    status: Literal["success"] = Field(..., description="Indica que a remoção foi aplicada.")


class SavedNotificationBulkDeleteResponse(BaseModel):
    """Confirmação da limpeza administrativa em lote."""

    status: Literal["success"] = Field(..., description="Indica que a limpeza foi aplicada.")
    deleted: int = Field(..., ge=0, description="Quantidade de registros removidos.")

class NotificationTypeUpdate(BaseModel):
    type: NotificationStatus = Field(
        ...,
        description=(
            "Novo estado da revisão. A criação pública aceita somente Pendente; "
            "Aprovada e Reprovada exigem a chave administrativa."
        ),
        examples=["Aprovada"],
    )
