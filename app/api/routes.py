"""
Rotas da API do Chatbot.

Define os endpoints principais:
- POST /chat: envia mensagem e recebe resposta
- GET /health: verifica status da aplicação
"""

import logging

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

logger = logging.getLogger(__name__)

router = APIRouter()


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
        
        # Gera resposta
        reply = await provider.generate(request.message, history, model_override=request.model_override)
        
        # Salva mensagem do usuário e resposta no histórico
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
            detail={
                "error": "provider_unavailable",
                "message": str(e),
            },
        )
    
    except ModelNotFoundError as e:
        logger.error(f"Model not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "model_not_found",
                "message": str(e),
            },
        )
    
    except LLMProviderError as e:
        logger.error(f"LLM provider error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "llm_error",
                "message": str(e),
            },
        )
    
    except Exception as e:
        logger.exception(f"Unexpected error in chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "Erro interno ao processar mensagem. Verifique os logs.",
            },
        )


@router.get(
    "/personas",
    response_model=list[PersonaResponse],
    summary="Listar personas disponíveis",
    description="Retorna a lista de personas para chat proativo.",
)
async def list_personas() -> list[PersonaResponse]:
    """Retorna lista de personas."""
    personas = PersonaService.get_personas()
    return [
        PersonaResponse(id=p.id, name=p.name, description=p.description)
        for p in personas
    ]


@router.get(
    "/target-profiles",
    response_model=list[TargetProfileResponse],
    summary="Listar perfis de usuários alvo",
    description="Retorna a lista de perfis de usuários para contexto da notificação.",
)
async def list_target_profiles() -> list[TargetProfileResponse]:
    """Retorna lista de perfis alvo."""
    profiles = PersonaService.get_target_profiles()
    return [
        TargetProfileResponse(id=p.id, name=p.name, description=p.description)
        for p in profiles
    ]


@router.post(
    "/chat/proactive",
    response_model=ChatResponse,
    summary="Gerar mensagem proativa",
    description="Gera uma mensagem inicial baseada na persona selecionada.",
)
async def chat_proactive(request: ProactiveChatRequest) -> ChatResponse:
    """
    Gera uma mensagem proativa.
    
    Não requer histórico anterior.
    """
    try:
        # Gera mensagem com overrides
        message = await PersonaService.generate_proactive_message(
            request.persona_id, 
            target_profile_id=request.target_profile_id,
            persona_override=request.persona_override,
            model_override=request.model_override
        )
        
        provider = get_llm_provider()
        
        # Identifica o modelo usado
        used_model = request.model_override if request.model_override else provider.model
        
        return ChatResponse(
            session_id="new-session", # Placeholder
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


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verificar status da aplicação",
    description="Retorna o status da aplicação e se o provider LLM está disponível.",
)
async def health() -> HealthResponse:
    """
    Verifica a saúde da aplicação.
    
    Retorna:
    - status: "healthy" se tudo ok, "degraded" se provider offline
    - provider: nome do provider configurado
    - model: nome do modelo configurado
    - provider_available: se o provider está respondendo
    """
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
                message=(
                    f"Provider '{provider.name}' não está respondendo. "
                    f"Verifique se está instalado e rodando."
                ),
            )
    
    except ValueError as e:
        # Provider não pode ser criado (ex: HF sem token)
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

@router.post(
    "/rag/search",
    response_model=RAGSearchResponse,
    summary="Buscar no RAG",
    description="Pesquisa diretamente na base de conhecimento vetorial (PDFs).",
)
async def semantic_search(request: RAGSearchRequest) -> RAGSearchResponse:
    """Pesquisa vetorial crua para o Frontend Visualizador."""
    try:
        results = search_with_metadata(request.query, k=request.k)
        return RAGSearchResponse(
            results=results,
            query_echo=request.query
        )
    except Exception as e:
        logger.exception(f"Erro na busca RAG: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "rag_search_error", "message": str(e)},
        )
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
