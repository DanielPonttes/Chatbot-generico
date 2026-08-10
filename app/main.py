"""
Chatbot Econômico - Aplicação Principal

Ponto de entrada da aplicação FastAPI.
Configura rotas, middleware, e lifecycle da aplicação.
"""

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.security import (
    RequestBodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    validate_runtime_security,
    verify_api_key,
)

# Diretório de arquivos estáticos
STATIC_DIR = Path(__file__).parent / "static"
from app.api.routes import router
from app.services.llm_provider import close_provider
from app.services.memory import close_memory_manager

# ==========================================
# Configuração de Logging
# ==========================================
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ==========================================
# Lifecycle da Aplicação
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.
    
    - Startup: loga configurações e inicializa serviços
    - Shutdown: libera recursos (conexões, arquivos)
    """
    # ----- STARTUP -----
    validate_runtime_security()
    logger.info("=" * 50)
    logger.info(f"🚀 Iniciando {settings.app_name}")
    logger.info(f"   Provider: {settings.llm_provider}")
    if settings.llm_provider == "ollama":
        logger.info(f"   Modelo: {settings.ollama_model}")
        logger.info(f"   Ollama URL: {settings.ollama_base_url}")
    elif settings.llm_provider == "google":
        logger.info(f"   Modelo: {settings.gemini_model}")
    else:
        logger.info(f"   Modelo: {settings.hf_model}")
    logger.info(f"   Memória: {'SQLite' if settings.use_sqlite else 'RAM'}")
    logger.info(f"   Max mensagens: {settings.memory_max_messages}")
    logger.info("=" * 50)
    
    # Initialize Saved Notifications DB
    from app.api.db import init_db
    init_db()
    
    yield
    
    # ----- SHUTDOWN -----
    logger.info("🛑 Encerrando aplicação...")
    await close_provider()
    close_memory_manager()
    logger.info("✅ Recursos liberados")


# ==========================================
# Criação da Aplicação FastAPI
# ==========================================
app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version="1.0.0",
    lifespan=lifespan,
    # As rotas de documentação são registradas abaixo para poderem passar
    # pela mesma política de autenticação da API.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    openapi_tags=[
        {
            "name": "chat",
            "description": "Endpoints de conversação",
        },
        {
            "name": "health",
            "description": "Monitoramento e health check",
        },
        {
            "name": "integrations",
            "description": "Exploração do PostgreSQL remoto e da API Spring Boot",
        },
    ],
)


# ==========================================
# Documentação protegível
# ==========================================
@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(verify_api_key)])
async def openapi_schema() -> JSONResponse:
    """Publica o contrato OpenAPI sem reintroduzir rotas fora de /v1."""
    return JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False, dependencies=[Depends(verify_api_key)])
async def swagger_ui() -> HTMLResponse:
    """Entrega o Swagger UI; a dependência permite protegê-lo em produção."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{settings.app_name} - Swagger UI",
    )


@app.get("/redoc", include_in_schema=False, dependencies=[Depends(verify_api_key)])
async def redoc_ui() -> HTMLResponse:
    """Entrega o ReDoc sob a mesma política do Swagger UI."""
    return get_redoc_html(
        openapi_url="/openapi.json",
        title=f"{settings.app_name} - ReDoc",
    )

# ==========================================
# Tratamento global de erros
# ==========================================
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Padroniza erros inesperados no mesmo envelope dos HTTPException da API."""
    logger.exception("Erro não tratado em %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "error": "internal_error",
                "message": "Erro interno inesperado. Consulte os logs da aplicação.",
            }
        },
    )


# ==========================================
# Middleware
# ==========================================
# CORS - origens configuráveis via CORS_ALLOW_ORIGINS ("*" só para dev)
def _parse_cors_origins(value: str) -> list[str]:
    """Converte a lista separada por vírgula em lista de origens ("*" se vazia)."""
    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    return origins or ["*"]


def _parse_allowed_hosts(value: str) -> list[str]:
    """Converte hosts sem aplicar o fallback permissivo reservado ao CORS."""
    return [host.strip() for host in value.split(",") if host.strip()]


allowed_hosts = _parse_allowed_hosts(settings.allowed_hosts)

# Rate limit por IP (ativo apenas quando RATE_LIMIT_PER_MINUTE > 0)
app.add_middleware(RateLimitMiddleware)
if "*" not in allowed_hosts:
    # Registrado depois do rate limit para ficar mais externo no Starlette;
    # hosts inválidos não consomem a cota.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RequestBodySizeLimitMiddleware,
    max_body_bytes=settings.max_request_body_bytes,
)

# CORS fica no middleware mais externo para também adicionar seus headers em
# respostas 429 geradas pelo rate limit.
cors_origins = _parse_cors_origins(settings.cors_allow_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-API-Key", "Authorization"],
)


# ==========================================
# Rotas
# ==========================================
# Versão atual (v1) — caminho recomendado para consumo público
app.include_router(router, prefix="/v1", tags=["chat"], dependencies=[Depends(verify_api_key)])

# Caminhos legados sem prefixo — mantidos por compatibilidade, ocultos do schema (deprecar futuramente)
app.include_router(router, tags=["chat"], dependencies=[Depends(verify_api_key)], include_in_schema=False)

# ==========================================
# Rota raiz (serve a interface de testes)
# ==========================================
@app.get("/", include_in_schema=False, dependencies=[Depends(verify_api_key)])
async def root():
    """Serve a página inicial."""
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/notifications", include_in_schema=False, dependencies=[Depends(verify_api_key)])
async def notifications_page():
    """Serve a interface de testes de notificações."""
    return FileResponse(STATIC_DIR / "notifications.html")

@app.get("/rag", include_in_schema=False, dependencies=[Depends(verify_api_key)])
async def rag_dashboard_page():
    """Serve o visualizador do RAG."""
    return FileResponse(STATIC_DIR / "rag.html")


# ==========================================
# Execução direta (opcional)
# ==========================================
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug" if settings.debug else "info",
    )
