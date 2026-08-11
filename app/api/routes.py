"""
Rotas da API do Chatbot.

Define os endpoints principais:
- POST /chat: envia mensagem e recebe resposta
- GET  /health: verifica status da aplicação
- POST /chat/proactive: gera mensagem proativa e a persiste com status "Pendente"
- PATCH /notifications/saved/{id}: avalia uma notificação (Aprovada / Reprovada)
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError as PydanticValidationError

from app.core.config import settings
from app.core.security import (
    API_KEY_HEADER_NAME,
    validate_model_override,
    verify_admin_api_key,
)
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    AdminStatusResponse,
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
    CanonicalActivitiesResponse,
    CanonicalMissionsResponse,
    CanonicalParameterDefinitionsResponse,
    CanonicalPresenceResponse,
    CanonicalTelemetryResponse,
    CanonicalUserProfileResponse,
    NotificationGenerateRequest,
    NotificationMissionCatalogResponse,
    NotificationMissionResponse,
    NotificationTypeResponse,
    SavedNotificationCreate,
    SavedNotificationCreateResponse,
    SavedNotificationResponse,
    NotificationReviewResponse,
    SavedNotificationDeleteResponse,
    SavedNotificationBulkDeleteResponse,
    NotificationTypeUpdate,
)
from app.services.llm_provider import (
    get_llm_provider,
    LLMProviderError,
    ProviderNotAvailableError,
    ModelNotFoundError,
)
from app.services.memory import get_memory_manager
from app.services.node_metrics import read_node_metrics
from app.services.persona_service import (
    NotificationContextValidationError,
    NotificationTypeNotFoundError,
    PersonaNotFoundError,
    PersonaService,
)
from app.services.notification_mission_catalog import (
    NotificationMissionNotFoundError,
    get_notification_mission_by_id,
    get_notification_missions,
    NOTIFICATION_MISSION_CATALOG,
)
from app.services.integration_catalog import (
    EndpointInvocationNotSupportedError,
    EndpointNotFoundError,
    RemoteDatabaseError,
    RemoteSpringApiError,
    get_remote_postgres_catalog_service,
    get_spring_api_catalog_service,
)
from app.services.canonical_context import (
    CanonicalContextNotFoundError,
    CanonicalContextSourceError,
    get_canonical_context_service,
)
from app.services.notification_context_assembler import (
    NotificationContextAssembler,
    NotificationContextConflictError,
    NotificationContextSelectionError,
    NotificationContextStateError,
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
admin_router = APIRouter()
public_router = APIRouter()


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

    validated_model_override = validate_model_override(request.model_override)

    try:
        # Obtém instâncias dos serviços
        provider = get_llm_provider()
        memory = get_memory_manager()

        # Recupera histórico formatado para o LLM
        history = memory.get_formatted_history(request.session_id)
        reply = await provider.generate(request.message, history, model_override=validated_model_override)

        # Gera resposta
        memory.add_message(request.session_id, "user", request.message)
        memory.add_message(request.session_id, "assistant", reply)

        logger.info(f"Chat response - session: {request.session_id}, reply length: {len(reply)}")

        used_model = validated_model_override if validated_model_override else provider.model

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


def _notification_mission_response(mission) -> NotificationMissionResponse:
    payload = mission.model_dump()
    template = (
        PersonaService.get_notification_type_by_id(mission.template_id)
        if mission.template_id
        else None
    )
    payload["template_required_context_vars"] = (
        template.required_context_vars if template else []
    )
    return NotificationMissionResponse(**payload)


@router.get(
    "/notifications/missions",
    response_model=NotificationMissionCatalogResponse,
    tags=["notifications"],
    summary="Listar catálogo de missões",
    description=(
        "Retorna as 64 missões normalizadas do documento MissõesXnotificaçõesV3. "
        "O catálogo separa as entradas fornecidas por outros componentes das "
        "entradas derivadas pelo agente. Uma missão catalog_only ainda não deve "
        "ser usada para geração automática."
    ),
    responses={200: {"description": "Catálogo versionado de missões"}},
)
async def list_notification_missions() -> NotificationMissionCatalogResponse:
    return NotificationMissionCatalogResponse(
        catalog_version=NOTIFICATION_MISSION_CATALOG.catalog_version,
        source_document=NOTIFICATION_MISSION_CATALOG.source_document,
        mission_count=NOTIFICATION_MISSION_CATALOG.mission_count,
        missions=[_notification_mission_response(item) for item in get_notification_missions()],
    )


@router.get(
    "/notifications/missions/{mission_id}",
    response_model=NotificationMissionResponse,
    tags=["notifications"],
    summary="Consultar uma missão",
    description=(
        "Retorna uma missão normalizada e seu mapeamento para o template técnico, "
        "quando disponível."
    ),
    responses={
        404: {"description": "Missão não encontrada", "model": ErrorResponse},
    },
)
async def get_notification_mission(mission_id: str) -> NotificationMissionResponse:
    try:
        return _notification_mission_response(get_notification_mission_by_id(mission_id))
    except NotificationMissionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "mission_not_found", "message": str(exc)},
        )


@router.get(
    "/notifications/types",
    response_model=list[NotificationTypeResponse],
    tags=["notifications"],
    summary="Listar templates de notificação",
    description=(
        "Retorna o catálogo dos templates de notificação proativa que o backend "
        "executa atualmente. Cada item informa o notification_type_id, a categoria "
        "e o subtipo alinhados ao documento de missões, além das variáveis obrigatórias "
        "e opcionais do contexto. Este endpoint descreve geração de candidatos; "
        "entrega push e disparo de eventos ainda não fazem parte da API v1."
    ),
    responses={
        200: {"description": "Catálogo de templates executáveis"},
    },
)
async def list_notification_types() -> list[NotificationTypeResponse]:
    """Publica os metadados de descoberta sem expor os prompts internos."""
    return [
        NotificationTypeResponse(
            id=notification_type.id,
            name=notification_type.name,
            category=notification_type.category,
            subtype=notification_type.subtype,
            description=notification_type.description,
            default_use_rag=notification_type.default_use_rag,
            required_context_vars=notification_type.required_context_vars,
            context_variables=notification_type.context_variables,
        )
        for notification_type in PersonaService.get_notification_types()
    ]


@router.post(
    "/notifications/generate",
    response_model=ChatResponse,
    tags=["notifications"],
    summary="Gerar notificação por missão",
    description=(
        "Resolve um mission_id do catálogo, aplica o template técnico associado "
        "e persiste a candidata como Pendente. O contexto deve conter as variáveis "
        "exigidas pelo template; o catálogo apenas descreve a origem e a finalidade "
        "das variáveis. use_canonical_context é opt-in e exige chave administrativa; "
        "nesse modo, somente snapshots fresh podem preencher campos observados e "
        "conflitos com valores enviados são rejeitados. Este endpoint ainda gera "
        "uma candidata, não entrega push."
    ),
    responses={
        200: {"description": "Notificação candidata gerada e persistida"},
        400: {
            "description": "Contexto/template incompatível, seletor ausente ou limite excedido",
            "model": ErrorResponse,
        },
        404: {"description": "Missão, persona ou template não encontrado", "model": ErrorResponse},
        409: {
            "description": "Missão não executável, conflito canônico ou snapshot não fresh",
            "model": ErrorResponse,
        },
        503: {"description": "Fonte canônica indisponível", "model": ErrorResponse},
        500: {"description": "Falha na geração ou persistência", "model": ErrorResponse},
    },
)
async def generate_notification(
    request: NotificationGenerateRequest,
    http_request: Request,
) -> ChatResponse:
    try:
        mission = get_notification_mission_by_id(request.mission_id)
    except NotificationMissionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "mission_not_found", "message": str(exc)},
        )

    if mission.execution_status != "mapped_template" or not mission.template_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "mission_not_executable",
                "message": (
                    f"A missão '{mission.mission_id}' está catalogada, mas ainda "
                    "não possui um template técnico executável."
                ),
            },
        )

    if request.notification_type_id and request.notification_type_id != mission.template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "mission_template_mismatch",
                "message": (
                    f"notification_type_id deve ser '{mission.template_id}' para a "
                    f"missão '{mission.mission_id}'."
                ),
            },
        )

    update: dict = {"notification_type_id": mission.template_id}
    if request.use_canonical_context:
        await verify_admin_api_key(
            http_request,
            http_request.headers.get(API_KEY_HEADER_NAME),
        )
        notification_type = PersonaService.get_notification_type_by_id(mission.template_id)
        allowed_fields = set(mission.context_variables)
        if notification_type:
            allowed_fields.update(notification_type.context_variables)

        assembler = NotificationContextAssembler(get_canonical_context_service())
        try:
            assembled = await asyncio.to_thread(
                assembler.assemble,
                provided_context=request.notification_context,
                allowed_fields=allowed_fields,
                pessoa_id=request.pessoa_id,
                room_id=request.room_id,
                sensor_external_id=request.sensor_external_id,
            )
        except NotificationContextSelectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "canonical_context_selector_required", "message": str(exc)},
            )
        except NotificationContextConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "canonical_context_conflict",
                    "message": str(exc),
                    "details": {"field": exc.field},
                },
            )
        except NotificationContextStateError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "canonical_context_not_fresh",
                    "message": str(exc),
                    "details": {
                        "scope": exc.scope,
                        "source_status": exc.source_status,
                    },
                },
            )
        except CanonicalContextNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "context_not_found", "message": str(exc)},
            )
        except CanonicalContextSourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "context_source_unavailable", "message": str(exc)},
            )

        update.update(
            {
                "notification_context": assembled.values,
                # Evita uma segunda consulta pelo enriquecedor legado best-effort.
                "pessoa_id": None,
                "room_id": None,
                "sensor_external_id": None,
            }
        )

    # model_validate reaplica os limites de 32 chaves/8 KiB após o merge.
    try:
        resolved_request = NotificationGenerateRequest.model_validate(
            {**request.model_dump(), **update}
        )
    except PydanticValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "canonical_context_limits_exceeded",
                "message": (
                    "O contexto combinado excede o limite de 32 chaves ou 8 KiB."
                ),
            },
        ) from exc
    response = await chat_proactive(resolved_request)
    if request.use_canonical_context:
        scope_types = sorted({scope.split(":", 1)[0] for scope in assembled.scopes})
        logger.info(
            "Contexto canônico usado na candidata id=%s; campos=%s; fontes=%s",
            response.session_id,
            ",".join(assembled.source_fields),
            ",".join(scope_types),
        )
    return response


# ---------------------------------------------------------------------------
# Chat proativo — gera E persiste automaticamente como "Pendente"
# ---------------------------------------------------------------------------

@router.post(
    "/chat/proactive",
    response_model=ChatResponse,
    tags=["notifications"],
    responses={
        200: {"description": "Notificação candidata gerada e persistida como Pendente"},
        400: {"description": "Contexto incompatível com o template escolhido", "model": ErrorResponse},
        404: {"description": "Persona ou tipo de notificação não encontrado", "model": ErrorResponse},
        500: {"description": "Falha na geração ou persistência", "model": ErrorResponse},
    },
    summary="Gerar mensagem proativa",
    description=(
        "Gera uma notificação candidata baseada na persona, no perfil-alvo, no "
        "notification_type_id e no contexto operacional enviado. O resultado é "
        "persistido automaticamente como 'Pendente' para avaliação posterior. "
        "Use GET /v1/notifications/types antes desta chamada para descobrir as "
        "variáveis obrigatórias. Os campos de sala, sensores, clima, consumo, "
        "recompensas e progresso seguem o catálogo de contexto do documento de missões."
    ),
)
async def chat_proactive(request: ProactiveChatRequest) -> ChatResponse:
    """
    Gera uma mensagem proativa e a salva automaticamente como "Pendente".

    O frontend pode depois chamar PATCH /notifications/saved/{id} para
    marcar a notificação como "Aprovada" ou "Reprovada".
    """
    validated_model_override = validate_model_override(request.model_override)

    try:
        # Gera mensagem com overrides e RAG
        result = await PersonaService.generate_proactive_message(
            request.persona_id, 
            target_profile_id=request.target_profile_id,
            persona_override=request.persona_override,
            model_override=validated_model_override,
            use_rag=request.use_rag,
            room_id=request.room_id,
            sensor_external_id=request.sensor_external_id,
            pessoa_id=request.pessoa_id,
            notification_type_id=request.notification_type_id,
            notification_context=request.notification_context,
        )

        provider = get_llm_provider()
        used_model = validated_model_override if validated_model_override else provider.model

        # ----------------------------------------------------------------
        # Persiste automaticamente com status "Pendente"
        # ----------------------------------------------------------------
        notification_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        # Contexto canônico pode conter dados pessoais mínimos e observações da
        # fonte. O prompt completo não é persistido nesse modo; a auditoria usa
        # somente campos/fontes sem IDs, registrada pela rota de missão.
        persist_prompt = (
            None
            if getattr(request, "use_canonical_context", False)
            else result.prompt_used
        )
        saved = save_notification({
            "id":             notification_id,
            "type":           "Pendente",
            "content":        result.message,
            "persona":        request.persona_id,
            "target_profile": request.target_profile_id,
            "prompt_used":    persist_prompt,
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

    except PersonaNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "persona_not_found", "message": str(e)},
        )
    except NotificationTypeNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "notification_type_not_found", "message": str(e)},
        )
    except (NotificationContextValidationError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "validation_error", "message": str(e)},
        )
    except Exception as e:
        logger.exception(f"Error in proactive chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Erro interno ao gerar a notificação. Consulte os logs.",
            },
        )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def _probe_external_components() -> dict[str, str]:
    """
    Verifica rapidamente os componentes externos (PostgreSQL e API Spring).
    Nunca levanta exceção — falhas viram strings de status no health.
    """
    components: dict[str, str] = {}

    try:
        get_remote_postgres_catalog_service().health()
        # O liveness público não deve revelar o nome do banco remoto.
        components["database"] = "connected"
    except Exception as exc:
        logger.warning("Database health probe failed: %s", exc)
        components["database"] = "unavailable"

    try:
        spring_info = get_spring_api_catalog_service().get_connection_info()
        probe_timeout = min(3.0, float(spring_info["timeout_seconds"]))
        with httpx.Client(timeout=httpx.Timeout(probe_timeout)) as client:
            response = client.get(f"{spring_info['base_url']}/actuator/health")
        components["spring_api"] = f"reachable (HTTP {response.status_code})"
    except Exception as exc:
        logger.warning("Spring health probe failed: %s", exc)
        components["spring_api"] = "unreachable"

    return components


async def _collect_health_status() -> HealthResponse:
    """Coleta o estado do runtime sem acoplar a lógica a uma rota HTTP."""
    # O probe usa clientes síncronos legados; isolá-lo em uma thread evita
    # bloquear o event loop público durante timeouts de integrações externas.
    components = await asyncio.to_thread(_probe_external_components)
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
                components=components,
            )
        else:
            return HealthResponse(
                status="degraded",
                provider=provider.name,
                model=provider.model,
                provider_available=False,
                message="Provider offline ou sem resposta.",
                components=components,
            )

    except ValueError as e:
        return HealthResponse(
            status="unhealthy",
            provider=settings.llm_provider,
            model=settings.ollama_model if settings.llm_provider == "ollama" else settings.hf_model,
            provider_available=False,
            message=str(e),
            components=components,
        )

    except Exception as e:
        logger.exception(f"Error in health check: {e}")
        return HealthResponse(
            status="unhealthy",
            provider=settings.llm_provider,
            model="unknown",
            provider_available=False,
            message=f"Erro ao verificar status: {e}",
            components=components,
        )


@public_router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verificar status da aplicação",
    description="Retorna o status da aplicação, do provider LLM e dos componentes externos.",
)
async def health() -> HealthResponse:
    return await _collect_health_status()


@admin_router.get(
    "/admin/status",
    response_model=AdminStatusResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["admin"],
    summary="Consultar status operacional detalhado",
    description=(
        "Retorna um resumo protegido do backend, do provider LLM e das "
        "integrações externas, além do snapshot local do host para o futuro "
        "painel administrativo. Não expõe credenciais nem permite acesso ao "
        "Docker socket."
    ),
)
async def admin_status(request: Request) -> AdminStatusResponse:
    """Expõe readiness detalhado somente para a chave administrativa."""
    health_status = await _collect_health_status()
    started_monotonic = getattr(request.app.state, "started_monotonic", time.monotonic())
    node_metrics = await asyncio.to_thread(read_node_metrics)
    return AdminStatusResponse(
        service=settings.app_name,
        status=health_status.status,
        provider=health_status.provider,
        model=health_status.model,
        provider_available=health_status.provider_available,
        components=health_status.components or {},
        checked_at=datetime.now(timezone.utc),
        uptime_seconds=round(max(0.0, time.monotonic() - started_monotonic), 3),
        node_metrics=node_metrics,
    )


@router.get(
    "/integrations/catalog",
    response_model=IntegrationsCatalogResponse,
    dependencies=[Depends(verify_admin_api_key)],
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


async def _read_canonical_context(callback):
    """Executa leitura síncrona do catálogo fora do event loop e normaliza falhas."""
    try:
        return await asyncio.to_thread(callback)
    except CanonicalContextNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "context_not_found", "message": str(exc)},
        ) from exc
    except CanonicalContextSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "context_source_unavailable", "message": str(exc)},
        ) from exc


@admin_router.get(
    "/context/users/{user_id}/profile",
    response_model=CanonicalUserProfileResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["context"],
    summary="Ler perfil mínimo do usuário",
    description=(
        "Retorna somente o identificador e o nome de exibição observados no "
        "PostgreSQL. E-mail, telefone, matrícula e senha não fazem parte do contrato."
    ),
)
async def canonical_user_profile(user_id: str) -> CanonicalUserProfileResponse:
    service = get_canonical_context_service()
    return CanonicalUserProfileResponse(
        **await _read_canonical_context(lambda: service.profile(user_id))
    )


@admin_router.get(
    "/context/users/{user_id}/activities",
    response_model=CanonicalActivitiesResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["context"],
    summary="Ler atividades observadas do usuário",
    description=(
        "Retorna atividades e o resumo por status. Os horários de cada atividade "
        "são preservados; a metadata descreve o freshness do snapshot consultado."
    ),
)
async def canonical_user_activities(
    user_id: str,
    limit: int = Query(default=50, ge=1, le=100),
) -> CanonicalActivitiesResponse:
    service = get_canonical_context_service()
    return CanonicalActivitiesResponse(
        **await _read_canonical_context(lambda: service.activities(user_id, limit=limit))
    )


@admin_router.get(
    "/context/rooms/{room_id}/telemetry/latest",
    response_model=CanonicalTelemetryResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["context"],
    summary="Ler a última telemetria observada da sala",
    description=(
        "Retorna a medição mais recente disponível para a sala, com unidades, "
        "instante observado e estado fresh/stale/empty."
    ),
)
async def canonical_room_telemetry(room_id: str) -> CanonicalTelemetryResponse:
    service = get_canonical_context_service()
    return CanonicalTelemetryResponse(
        **await _read_canonical_context(lambda: service.room_telemetry(room_id))
    )


@admin_router.get(
    "/context/sensors/{sensor_id}/telemetry/latest",
    response_model=CanonicalTelemetryResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["context"],
    summary="Ler a última telemetria observada do sensor",
    description=(
        "Retorna a medição mais recente disponível para o sensor, sem permitir "
        "que o modelo preencha métricas ausentes."
    ),
)
async def canonical_sensor_telemetry(sensor_id: str) -> CanonicalTelemetryResponse:
    service = get_canonical_context_service()
    return CanonicalTelemetryResponse(
        **await _read_canonical_context(lambda: service.sensor_telemetry(sensor_id))
    )


@admin_router.get(
    "/context/rooms/{room_id}/presence",
    response_model=CanonicalPresenceResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["context"],
    summary="Ler o snapshot agregado de presença da sala",
    description=(
        "Retorna ocupação agregada, capacidade e percentual quando a capacidade "
        "está cadastrada. Identificadores de pessoas nunca são retornados."
    ),
)
async def canonical_room_presence(room_id: str) -> CanonicalPresenceResponse:
    service = get_canonical_context_service()
    return CanonicalPresenceResponse(
        **await _read_canonical_context(lambda: service.room_presence(room_id))
    )


@admin_router.get(
    "/context/missions",
    response_model=CanonicalMissionsResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["context"],
    summary="Ler missões da fonte canônica",
    description=(
        "Lista missões remotas com limite explícito. A geração de notificações "
        "continua sujeita ao catálogo local e às regras de mapeamento."
    ),
)
async def canonical_missions(
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=100),
) -> CanonicalMissionsResponse:
    service = get_canonical_context_service()
    return CanonicalMissionsResponse(
        **await _read_canonical_context(
            lambda: service.missions(active_only=active_only, limit=limit)
        )
    )


@admin_router.get(
    "/context/rules/parameter-definitions",
    response_model=CanonicalParameterDefinitionsResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["context"],
    summary="Ler definições de parâmetros de regras",
    description=(
        "Retorna tipos, unidades e nomes de parâmetros observados. Não retorna "
        "valores de telemetria nem executa regras."
    ),
)
async def canonical_parameter_definitions(
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=100),
) -> CanonicalParameterDefinitionsResponse:
    service = get_canonical_context_service()
    return CanonicalParameterDefinitionsResponse(
        **await _read_canonical_context(
            lambda: service.parameter_definitions(active_only=active_only, limit=limit)
        )
    )


@router.get(
    "/integrations/database/tables",
    response_model=RemoteDatabaseCatalogResponse,
    dependencies=[Depends(verify_admin_api_key)],
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
    dependencies=[Depends(verify_admin_api_key)],
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
    dependencies=[Depends(verify_admin_api_key)],
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
    dependencies=[Depends(verify_admin_api_key)],
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
    dependencies=[Depends(verify_admin_api_key)],
    tags=["integrations"],
    summary="Buscar pessoas para autocomplete (admin)",
    description="Busca somente por identificador/nome e não retorna e-mail, telefone ou matrícula.",
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
    dependencies=[Depends(verify_admin_api_key)],
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
            detail={
                "error": "rag_search_error",
                "message": "Erro interno na busca RAG. Consulte os logs.",
            },
        )


# ---------------------------------------------------------------------------
# Notificações salvas
# ---------------------------------------------------------------------------

@router.get(
    "/notifications/saved",
    response_model=list[SavedNotificationResponse],
    tags=["notifications"],
    summary="Listar notificações salvas",
    description=(
        "Retorna os candidatos e resultados de revisão humana nos estados "
        "Pendente, Aprovada ou Reprovada, ordenados do mais recente para o mais antigo."
    ),
)
async def list_saved_notifications():
    return get_all_saved_notifications()


@router.post(
    "/notifications/saved",
    response_model=SavedNotificationCreateResponse,
    tags=["notifications"],
    summary="Salvar notificação manualmente",
    description=(
        "Salva uma notificação candidata no SQLite. A criação pública força o estado "
        "Pendente; a aprovação ou reprovação ocorre no endpoint administrativo de revisão."
    ),
    responses={
        400: {"description": "Falha ao salvar ou ID duplicado", "model": ErrorResponse},
    },
)
async def create_saved_notification(request: SavedNotificationCreate) -> SavedNotificationCreateResponse:
    success = save_notification(request.model_dump())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "notification_save_failed",
                "message": "Não foi possível salvar a notificação (ID duplicado ou erro).",
            },
        )
    return SavedNotificationCreateResponse(status="success")


@router.patch(
    "/notifications/saved/{notif_id}",
    response_model=NotificationReviewResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["notifications"],
    summary="Avaliar notificação",
    description=(
        "Atualiza o status de uma notificação para 'Aprovada' ou 'Reprovada'. "
        "Também aceita reverter para 'Pendente'."
    ),
    responses={
        404: {"description": "Notificação inexistente ou estado inválido", "model": ErrorResponse},
    },
)
async def evaluate_notification(notif_id: str, request: NotificationTypeUpdate) -> NotificationReviewResponse:
    """
    Endpoint de avaliação.  O frontend chama este endpoint após o usuário
    clicar em Aprovar / Reprovar em uma notificação com status 'Pendente'.
    """
    success = update_notification_type(notif_id, request.type)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "notification_not_found_or_invalid_type",
                "message": "Notificação não encontrada ou tipo inválido.",
            },
        )
    return NotificationReviewResponse(status="success", id=notif_id, type=request.type)


@router.delete(
    "/notifications/saved/all",
    response_model=SavedNotificationBulkDeleteResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["notifications"],
    summary="Limpar todas as notificações salvas",
    description="Remove todos os candidatos salvos; exige a chave administrativa.",
)
async def clear_saved_notifications() -> SavedNotificationBulkDeleteResponse:
    deleted_count = clear_all_notifications()
    return SavedNotificationBulkDeleteResponse(status="success", deleted=deleted_count)


@router.delete(
    "/notifications/saved/{notif_id}",
    response_model=SavedNotificationDeleteResponse,
    dependencies=[Depends(verify_admin_api_key)],
    tags=["notifications"],
    summary="Deletar uma notificação salva específica",
    description="Remove um candidato salvo pelo ID; exige a chave administrativa.",
    responses={
        404: {"description": "Notificação inexistente", "model": ErrorResponse},
    },
)
async def delete_saved_notification(notif_id: str) -> SavedNotificationDeleteResponse:
    success = delete_notification(notif_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "notification_delete_failed",
                "message": "Notificação não encontrada ou erro ao deletar.",
            },
        )
    return SavedNotificationDeleteResponse(status="success")
