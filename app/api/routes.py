"""
Rotas da API do Chatbot.

Define os endpoints principais:
- POST /chat: envia mensagem e recebe resposta
- GET  /health: verifica status da aplicação
- POST /chat/proactive: gera mensagem proativa e a persiste com status "Pendente"
- PATCH /notifications/saved/{id}: avalia uma notificação (Aprovada / Reprovada)
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ErrorResponse,
    PersonaResponse,
    TargetProfileResponse,
    ProactiveChatRequest,
    RAGSearchRequest,
    RAGSearchResponse,
    RemoteDatabaseCatalogResponse,
    RemoteDatabaseRowsResponse,
    RemoteDatabaseTableDetailResponse,
    SpringApiCatalogResponse,
    ContextLookupOptionResponse,
    SpringEndpointInvokeRequest,
    SpringEndpointInvokeResponse,
    IntegrationsCatalogResponse,
    SavedNotificationCreate,
    SavedNotificationResponse,
    NotificationTypeUpdate,
)
from app.services.llm_provider import (
    get_llm_provider,
    LLMProviderError,
    ProviderNotAvailableError,
    ModelNotFoundError,
)
from app.services.memory import get_memory_manager
from app.services.persona_service import PersonaService
from app.services.integration_catalog import (
    EndpointInvocationNotSupportedError,
    EndpointNotFoundError,
    RemoteDatabaseError,
    RemoteSpringApiError,
    get_remote_postgres_catalog_service,
    get_spring_api_catalog_service,
)
from app.rag.retriever import search_with_metadata
from app.api.db import (
    get_all_saved_notifications,
    save_notification,
    update_notification_type,
    delete_notification,
    clear_all_notifications,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        200: {"description": "Resposta gerada com sucesso"},
        503: {"model": ErrorResponse, "description": "Provider LLM não disponível"},
        500: {"model": ErrorResponse, "description": "Erro interno"},
    },
    summary="Enviar mensagem ao chatbot",
    description=(
        "Envia uma mensagem para o chatbot e recebe uma resposta. "
        "O histórico da conversa é mantido por session_id."
    ),
)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Processa uma mensagem do usuário e retorna a resposta do chatbot.

    O endpoint:
    1. Recupera o histórico da sessão
    2. Envia a mensagem + histórico para o provider LLM
    3. Salva tanto a mensagem quanto a resposta no histórico
    4. Retorna a resposta
    """
    logger.info(f"Chat request - session: {request.session_id}, message length: {len(request.message)}")

    try:
        # Obtém instâncias dos serviços
        provider = get_llm_provider()
        memory = get_memory_manager()

        # Recupera histórico formatado para o LLM
        history = memory.get_formatted_history(request.session_id)
        reply = await provider.generate(request.message, history, model_override=request.model_override)

        # Gera resposta
        memory.add_message(request.session_id, "user", request.message)
        memory.add_message(request.session_id, "assistant", reply)

        logger.info(f"Chat response - session: {request.session_id}, reply length: {len(reply)}")

        used_model = request.model_override if request.model_override else provider.model

        return ChatResponse(
            session_id=request.session_id,
            reply=reply,
            provider=provider.name,
            model=used_model,
        )

    except ProviderNotAvailableError as e:
        logger.error(f"Provider not available: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "provider_unavailable", "message": str(e)},
        )

    except ModelNotFoundError as e:
        logger.error(f"Model not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "model_not_found", "message": str(e)},
        )

    except LLMProviderError as e:
        logger.error(f"LLM provider error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "llm_error", "message": str(e)},
        )

    except Exception as e:
        logger.exception(f"Unexpected error in chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Erro interno ao processar mensagem. Verifique os logs."},
        )


# ---------------------------------------------------------------------------
# Personas / Target Profiles
# ---------------------------------------------------------------------------

@router.get(
    "/personas",
    response_model=list[PersonaResponse],
    summary="Listar personas disponíveis",
    description="Retorna a lista de personas para chat proativo.",
)
async def list_personas() -> list[PersonaResponse]:
    personas = PersonaService.get_personas()
    return [PersonaResponse(id=p.id, name=p.name, description=p.description) for p in personas]


@router.get(
    "/target-profiles",
    response_model=list[TargetProfileResponse],
    summary="Listar perfis de usuários alvo",
    description="Retorna a lista de perfis de usuários para contexto da notificação.",
)
async def list_target_profiles() -> list[TargetProfileResponse]:
    profiles = PersonaService.get_target_profiles()
    return [TargetProfileResponse(id=p.id, name=p.name, description=p.description) for p in profiles]


# ---------------------------------------------------------------------------
# Chat proativo — gera E persiste automaticamente como "Pendente"
# ---------------------------------------------------------------------------

@router.post(
    "/chat/proactive",
    response_model=ChatResponse,
    summary="Gerar mensagem proativa",
    description=(
        "Gera uma mensagem inicial baseada na persona selecionada e a persiste "
        "automaticamente no banco com status 'Pendente' para avaliação posterior."
    ),
)
async def chat_proactive(request: ProactiveChatRequest) -> ChatResponse:
    """
    Gera uma mensagem proativa e a salva automaticamente como "Pendente".

    O frontend pode depois chamar PATCH /notifications/saved/{id} para
    marcar a notificação como "Aprovada" ou "Reprovada".
    """
    try:
        # Gera mensagem com overrides e RAG
        result = await PersonaService.generate_proactive_message(
            request.persona_id, 
            target_profile_id=request.target_profile_id,
            persona_override=request.persona_override,
            model_override=request.model_override,
            use_rag=request.use_rag,
            room_id=request.room_id,
            sensor_external_id=request.sensor_external_id,
            pessoa_id=request.pessoa_id,
            notification_type_id=request.notification_type_id,
            notification_context=request.notification_context,
        )

        provider = get_llm_provider()
        used_model = request.model_override if request.model_override else provider.model

        # ----------------------------------------------------------------
        # Persiste automaticamente com status "Pendente"
        # ----------------------------------------------------------------
        notification_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        saved = save_notification({
            "id":             notification_id,
            "type":           "Pendente",
            "content":        result.message,
            "persona":        request.persona_id,
            "target_profile": request.target_profile_id,
            "prompt_used":    result.prompt_used,
            "model":          used_model,
            "date":           now_iso,
        })

        if not saved:
            logger.warning(f"Não foi possível persistir notificação proativa id={notification_id}")

        return ChatResponse(
            session_id=notification_id,
            reply=result.message,
            provider=provider.name,
            model=used_model,
            context_summary=result.context_summary,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "persona_not_found", "message": str(e)},
        )
    except Exception as e:
        logger.exception(f"Error in proactive chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": str(e)},
        )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verificar status da aplicação",
    description="Retorna o status da aplicação e se o provider LLM está disponível.",
)
async def health() -> HealthResponse:
    try:
        provider = get_llm_provider()
        is_available = await provider.is_available()

        if is_available:
            return HealthResponse(
                status="healthy",
                provider=provider.name,
                model=provider.model,
                provider_available=True,
                message=None,
            )
        else:
            return HealthResponse(
                status="degraded",
                provider=provider.name,
                model=provider.model,
                provider_available=False,
                message="Provider offline ou sem resposta.",
            )

    except ValueError as e:
        return HealthResponse(
            status="unhealthy",
            provider=settings.llm_provider,
            model=settings.ollama_model if settings.llm_provider == "ollama" else settings.hf_model,
            provider_available=False,
            message=str(e),
        )

    except Exception as e:
        logger.exception(f"Error in health check: {e}")
        return HealthResponse(
            status="unhealthy",
            provider=settings.llm_provider,
            model="unknown",
            provider_available=False,
            message=f"Erro ao verificar status: {e}",
        )


@router.get(
    "/integrations/catalog",
    response_model=IntegrationsCatalogResponse,
    tags=["integrations"],
    summary="Visão consolidada das integrações externas",
    description=(
        "Lista o catálogo do PostgreSQL remoto e da API Spring Boot, "
        "além de destacar os recursos mais relevantes para o projeto atual."
    ),
)
async def get_integrations_catalog() -> IntegrationsCatalogResponse:
    db_service = get_remote_postgres_catalog_service()
    spring_service = get_spring_api_catalog_service()

    try:
        db_connection = db_service.health()
        db_tables = db_service.list_tables()
    except RemoteDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "remote_database_unavailable", "message": str(e)},
        )

    spring_endpoints = spring_service.list_endpoints()

    recommended_tables = [
        table for table in db_tables if table["relevance_score"] >= 90
    ][:6]
    recommended_endpoints = [
        endpoint for endpoint in spring_endpoints if endpoint["relevance_score"] >= 90
    ][:8]

    return IntegrationsCatalogResponse(
        database={
            "connection": db_connection,
            "tables": db_tables,
        },
        spring_api={
            "connection": spring_service.get_connection_info(),
            "endpoints": spring_endpoints,
        },
        recommendations={
            "database_tables": recommended_tables,
            "spring_endpoints": recommended_endpoints,
        },
    )


@router.get(
    "/integrations/database/tables",
    response_model=RemoteDatabaseCatalogResponse,
    tags=["integrations"],
    summary="Listar tabelas do PostgreSQL remoto",
    description=(
        "Retorna as tabelas disponíveis em `procel_analytics`, com categoria, "
        "estimativa de linhas e relevância para este projeto."
    ),
)
async def list_remote_database_tables() -> RemoteDatabaseCatalogResponse:
    service = get_remote_postgres_catalog_service()

    try:
        return RemoteDatabaseCatalogResponse(
            connection=service.health(),
            tables=service.list_tables(),
        )
    except RemoteDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "remote_database_unavailable", "message": str(e)},
        )


@router.get(
    "/integrations/database/tables/{schema_name}/{table_name}",
    response_model=RemoteDatabaseTableDetailResponse,
    tags=["integrations"],
    summary="Descrever uma tabela do PostgreSQL remoto",
    description="Expande as colunas, chaves primárias e referências de uma tabela remota.",
)
async def describe_remote_database_table(
    schema_name: str,
    table_name: str,
) -> RemoteDatabaseTableDetailResponse:
    service = get_remote_postgres_catalog_service()

    try:
        return RemoteDatabaseTableDetailResponse(**service.describe_table(schema_name, table_name))
    except RemoteDatabaseError as e:
        is_missing_table = "Tabela não encontrada" in str(e)
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if is_missing_table
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail={
                "error": (
                    "remote_table_not_found"
                    if is_missing_table
                    else "remote_database_unavailable"
                ),
                "message": str(e),
            },
        )


@router.get(
    "/integrations/database/tables/{schema_name}/{table_name}/rows",
    response_model=RemoteDatabaseRowsResponse,
    tags=["integrations"],
    summary="Amostrar registros de uma tabela remota",
    description="Lê um subconjunto paginado de linhas do PostgreSQL remoto.",
)
async def preview_remote_database_rows(
    schema_name: str,
    table_name: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RemoteDatabaseRowsResponse:
    service = get_remote_postgres_catalog_service()

    try:
        return RemoteDatabaseRowsResponse(
            **service.preview_rows(schema_name, table_name, limit=limit, offset=offset)
        )
    except RemoteDatabaseError as e:
        is_missing_table = "Tabela não encontrada" in str(e)
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if is_missing_table
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail={
                "error": (
                    "remote_table_not_found"
                    if is_missing_table
                    else "remote_database_unavailable"
                ),
                "message": str(e),
            },
        )


@router.get(
    "/integrations/spring/endpoints",
    response_model=SpringApiCatalogResponse,
    tags=["integrations"],
    summary="Listar endpoints da API Spring Boot",
    description=(
        "Lista os endpoints confirmados no Spring Boot remoto e também os observados "
        "na coleção/Postman, indicando se a invocação automática já é suportada."
    ),
)
async def list_spring_endpoints() -> SpringApiCatalogResponse:
    service = get_spring_api_catalog_service()
    return SpringApiCatalogResponse(
        connection=service.get_connection_info(),
        endpoints=service.list_endpoints(),
    )


@router.get(
    "/integrations/context/rooms",
    response_model=list[ContextLookupOptionResponse],
    tags=["integrations"],
    summary="Buscar salas/compartimentos para autocomplete",
)
async def lookup_rooms(
    query: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[ContextLookupOptionResponse]:
    service = get_remote_postgres_catalog_service()

    try:
        return [ContextLookupOptionResponse(**item) for item in service.search_rooms(query, limit)]
    except RemoteDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "remote_database_unavailable", "message": str(e)},
        )


@router.get(
    "/integrations/context/sensors",
    response_model=list[ContextLookupOptionResponse],
    tags=["integrations"],
    summary="Buscar sensores para autocomplete",
)
async def lookup_sensors(
    query: str = Query(default="", max_length=100),
    room_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[ContextLookupOptionResponse]:
    service = get_remote_postgres_catalog_service()

    try:
        return [
            ContextLookupOptionResponse(**item)
            for item in service.search_sensors(query, room_id=room_id, limit=limit)
        ]
    except RemoteDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "remote_database_unavailable", "message": str(e)},
        )


@router.get(
    "/integrations/context/people",
    response_model=list[ContextLookupOptionResponse],
    tags=["integrations"],
    summary="Buscar pessoas para autocomplete",
)
async def lookup_people(
    query: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[ContextLookupOptionResponse]:
    service = get_remote_postgres_catalog_service()

    try:
        return [ContextLookupOptionResponse(**item) for item in service.search_people(query, limit)]
    except RemoteDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "remote_database_unavailable", "message": str(e)},
        )


@router.post(
    "/integrations/spring/endpoints/{endpoint_id}/invoke",
    response_model=SpringEndpointInvokeResponse,
    tags=["integrations"],
    summary="Invocar um endpoint catalogado da API Spring",
    description=(
        "Executa uma chamada controlada contra um endpoint remoto da API Spring Boot "
        "a partir do catálogo local."
    ),
)
async def invoke_spring_endpoint(
    endpoint_id: str,
    request: SpringEndpointInvokeRequest,
) -> SpringEndpointInvokeResponse:
    service = get_spring_api_catalog_service()

    try:
        response = service.invoke_endpoint(
            endpoint_id=endpoint_id,
            path_params=request.path_params,
            query_params=request.query_params,
            body=request.body,
        )
        return SpringEndpointInvokeResponse(**response)
    except EndpointNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "spring_endpoint_not_found", "message": str(e)},
        )
    except EndpointInvocationNotSupportedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "spring_endpoint_not_invokable", "message": str(e)},
        )
    except RemoteSpringApiError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "spring_api_error", "message": str(e)},
        )

# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

@router.post(
    "/rag/search",
    response_model=RAGSearchResponse,
    summary="Buscar no RAG",
    description="Pesquisa diretamente na base de conhecimento vetorial (PDFs).",
)
async def semantic_search(request: RAGSearchRequest) -> RAGSearchResponse:
    try:
        results = search_with_metadata(request.query, k=request.k)
        return RAGSearchResponse(results=results, query_echo=request.query)
    except Exception as e:
        logger.exception(f"Erro na busca RAG: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "rag_search_error", "message": str(e)},
        )


# ---------------------------------------------------------------------------
# Notificações salvas
# ---------------------------------------------------------------------------

@router.get(
    "/notifications/saved",
    response_model=list[SavedNotificationResponse],
    summary="Listar notificações salvas",
    description="Retorna todas as notificações (Pendente, Aprovada, Reprovada).",
)
async def list_saved_notifications():
    return get_all_saved_notifications()


@router.post(
    "/notifications/saved",
    response_model=dict,
    summary="Salvar notificação manualmente",
    description="Salva uma notificação no banco de dados SQLite.",
)
async def create_saved_notification(request: SavedNotificationCreate):
    success = save_notification(request.model_dump())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível salvar a notificação (ID duplicado ou erro).",
        )
    return {"status": "success"}


@router.patch(
    "/notifications/saved/{notif_id}",
    response_model=dict,
    summary="Avaliar notificação",
    description=(
        "Atualiza o status de uma notificação para 'Aprovada' ou 'Reprovada'. "
        "Também aceita reverter para 'Pendente'."
    ),
)
async def evaluate_notification(notif_id: str, request: NotificationTypeUpdate):
    """
    Endpoint de avaliação.  O frontend chama este endpoint após o usuário
    clicar em Aprovar / Reprovar em uma notificação com status 'Pendente'.
    """
    success = update_notification_type(notif_id, request.type)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificação não encontrada ou tipo inválido.",
        )
    return {"status": "success", "id": notif_id, "type": request.type}


@router.delete(
    "/notifications/saved/all",
    response_model=dict,
    summary="Limpar todas as notificações salvas",
)
async def clear_saved_notifications():
    deleted_count = clear_all_notifications()
    return {"status": "success", "deleted": deleted_count}


@router.delete(
    "/notifications/saved/{notif_id}",
    response_model=dict,
    summary="Deletar uma notificação salva específica",
)
async def delete_saved_notification(notif_id: str):
    success = delete_notification(notif_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificação não encontrada ou erro ao deletar.",
        )
    return {"status": "success"}
