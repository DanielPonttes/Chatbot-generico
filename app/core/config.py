"""
Configurações da aplicação usando Pydantic Settings.

Todas as configurações podem ser definidas via variáveis de ambiente
ou arquivo .env na raiz do projeto.
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurações centralizadas da aplicação.
    
    Carrega valores de variáveis de ambiente ou arquivo .env.
    Valores padrão são otimizados para execução local econômica.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ==========================================
    # Provider LLM
    # ==========================================
    llm_provider: Literal["ollama", "huggingface"] = "ollama"
    """Provider de LLM: 'ollama' (local, gratuito) ou 'huggingface' (API externa)."""
    
    # ==========================================
    # Configurações Ollama
    # ==========================================
    ollama_base_url: str = "http://localhost:11434"
    """URL base do servidor Ollama local."""
    
    ollama_model: str = "qwen2.5:0.5b"
    """
    Modelo Ollama a usar. Opções recomendadas (leves):
    - qwen2.5:0.5b  (500M params, ~400MB) - PADRÃO
    - qwen2.5:1.5b  (1.5B params, ~1GB)
    - llama3.2:1b   (1B params, ~700MB)
    - phi3:mini     (3.8B params, ~2GB)
    """
    
    # ==========================================
    # Configurações HuggingFace
    # ==========================================
    hf_token: str | None = None
    """Token de autenticação HuggingFace. Obtenha em: https://huggingface.co/settings/tokens"""
    
    hf_model: str = "microsoft/DialoGPT-small"
    """Modelo HuggingFace para inferência via API."""
    
    # ==========================================
    # Configurações do Bot
    # ==========================================
    bot_system_prompt: str = (
        "Você é um assistente virtual amigável e prestativo. "
        "Responda sempre em português brasileiro de forma clara e objetiva."
    )
    """System prompt que define a persona/comportamento do bot."""
    
    # ==========================================
    # Configurações de Memória
    # ==========================================
    memory_max_messages: int = 10
    """Número máximo de mensagens mantidas no histórico por sessão."""
    
    use_sqlite: bool = False
    """Se True, persiste conversas em SQLite. Se False, mantém apenas em memória."""
    
    sqlite_path: str = "./data/conversations.db"
    """Caminho do arquivo SQLite (usado apenas se use_sqlite=True)."""
    
    # ==========================================
    # Configurações do Servidor
    # ==========================================
    app_name: str = "Chatbot Econômico"
    """Nome da aplicação exibido na documentação."""
    
    app_description: str = (
        "API de chatbot econômico para projetos de faculdade. "
        "Suporta Ollama (local) e HuggingFace (API) como providers de LLM."
    )
    """Descrição da aplicação exibida na documentação."""
    
    debug: bool = False
    """Modo debug - ativa logs mais detalhados."""


# Instância global de configurações (singleton)
settings = Settings()
