"""
Chatbot Econômico - Aplicação Principal

Ponto de entrada da aplicação FastAPI.
Configura rotas, middleware, e lifecycle da aplicação.
"""

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings

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
    ],
)

# ==========================================
# Middleware
# ==========================================
# CORS - permite requisições de qualquer origem (ajuste em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especifique as origens permitidas
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Rotas
# ==========================================
app.include_router(router, tags=["chat"])


# A tela de conversa foi removida.
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
