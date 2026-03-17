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

from fastapi import APIRouter, HTTPException, status

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
    SavedNotificationCreate,
    SavedNotificationResponse,
    NotificationTypeUpdate,       # novo schema — ver nota abaixo
)
from app.services.llm_provider import (
    get_llm_provider,
    LLMProviderError,
    ProviderNotAvailableError,
    ModelNotFoundError,
)
from app.services.memory import get_memory_manager
from app.services.persona_service import PersonaService
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
        # generate_proactive_message agora retorna (message, prompt_used)
        # Ver nota em persona_service.py
        message, prompt_used = await PersonaService.generate_proactive_message(
            request.persona_id,
            target_profile_id=request.target_profile_id,
            persona_override=request.persona_override,
            model_override=request.model_override,
            use_rag=request.use_rag,
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
            "content":        message,
            "persona":        request.persona_id,
            "target_profile": request.target_profile_id,
            "prompt_used":    prompt_used,
            "model":          used_model,
            "date":           now_iso,
        })

        if not saved:
            logger.warning(f"Não foi possível persistir notificação proativa id={notification_id}")

        return ChatResponse(
            session_id=notification_id,   # reutilizamos o ID gerado como session_id
            reply=message,
            provider=provider.name,
            model=used_model,
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
