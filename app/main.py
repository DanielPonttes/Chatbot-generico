"""
Chatbot Econômico - Aplicação Principal

Ponto de entrada da aplicação FastAPI.
Configura rotas, middleware, e lifecycle da aplicação.
"""

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.core.security import RateLimitMiddleware, verify_api_key

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
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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
# CORS - origens configuráveis via CORS_ALLOW_ORIGINS ("*" libera tudo, modo dev)
def _parse_cors_origins(value: str) -> list[str]:
    """Converte a lista separada por vírgula em lista de origens ("*" se vazia)."""
    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    return origins or ["*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(settings.cors_allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limit por IP (ativo apenas quando RATE_LIMIT_PER_MINUTE > 0)
app.add_middleware(RateLimitMiddleware)


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
@app.get("/", include_in_schema=False)
async def root():
    """Serve a página inicial."""
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/notifications", include_in_schema=False)
async def notifications_page():
    """Serve a interface de testes de notificações."""
    return FileResponse(STATIC_DIR / "notifications.html")

@app.get("/rag", include_in_schema=False)
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
