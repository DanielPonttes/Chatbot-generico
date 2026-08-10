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
    llm_provider: Literal["ollama", "huggingface", "google"] = "ollama"
    """Provider de LLM: 'ollama' (local), 'huggingface' (API), ou 'google' (Gemini)."""
    
    # ==========================================
    # Configurações Ollama
    # ==========================================
    ollama_base_url: str = "http://localhost:11434"
    """URL base do servidor Ollama local."""
    
    ollama_model: str = "qwen3.5:4b"
    """
    Modelo Ollama a usar. Opções recomendadas:
    - qwen3.5:4b     (Qwen3.5-4B, 4B params, ~3.3GB) - PADRÃO - melhor qualidade ate 8B
    - qwen2.5:7b    (7B params, ~4.7GB) - excelente em PT-BR
    - llama3.1:8b   (8B params, ~4.9GB) - generalista muito capaz
    - qwen2.5:0.5b  (500M params, ~400MB) - ultra-leve
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
    # Configurações Google Gemini
    # ==========================================
    gemini_api_key: str | None = None
    """API Key do Google Gemini."""

    gemini_model: str = "gemini-3-flash-preview"
    """Modelo Gemini a usar (ex: gemini-1.5-flash, gemini-3-flash-preview)."""
    
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

    # ==========================================
    # API Pública
    # ==========================================
    environment: Literal["development", "test", "staging", "production"] = "development"
    """Ambiente de execução; produção aplica validações fail-closed."""

    api_key: str | None = None
    """
    Chave de acesso da API (header X-API-Key).
    Se None (padrão), a autenticação fica desabilitada (modo desenvolvimento).
    """

    admin_api_key: str | None = None
    """Chave separada para operações administrativas/destrutivas."""

    cors_allow_origins: str = "*"
    """
    Origens permitidas no CORS, separadas por vírgula.
    "*" (padrão) libera qualquer origem — restrinja em produção.
    """

    rate_limit_per_minute: int = 0
    """
    Limite de requisições por minuto por IP. 0 (padrão) desativa.
    Observação: o contador é em memória, por processo/worker.
    """

    max_request_body_bytes: int = 2 * 1024 * 1024
    """Tamanho máximo de corpo HTTP aceito pelo backend, em bytes."""

    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    """Hosts aceitos pelo servidor, separados por vírgula."""

    trusted_proxy_networks: str = ""
    """Redes/IPs de proxies autorizados a informar X-Forwarded-For/Proto."""

    docs_public: bool = True
    """Mantém Swagger/ReDoc públicos em desenvolvimento; proteja na borda em produção."""

    legacy_routes_enabled: bool = True
    """Mantém as rotas sem /v1 durante a migração; desative em produção."""

    allow_model_override: bool = True
    """Permite que o cliente escolha um modelo por requisição (somente com allowlist em produção)."""

    allowed_models: str = ""
    """Modelos permitidos em model_override, separados por vírgula; vazio não restringe em dev."""

    # ==========================================
    # Integrações Externas - PostgreSQL Remoto
    # ==========================================
    remote_pg_host: str = "srv1428963.hstgr.cloud"
    """Host do PostgreSQL remoto."""

    remote_pg_port: int = 5432
    """Porta do PostgreSQL remoto."""

    remote_pg_user: str = "postgres"
    """Usuário de leitura/escrita do PostgreSQL remoto."""

    remote_pg_password: str | None = None
    """Senha do PostgreSQL remoto."""

    remote_pg_database: str = "procel_analytics"
    """Banco de dados principal com medições e ocupação."""

    remote_pg_sslmode: Literal["disable", "allow", "prefer", "require"] = "prefer"
    """Modo SSL usado na conexão com o PostgreSQL remoto."""

    remote_pg_connect_timeout: int = 5
    """Timeout de conexão com o PostgreSQL remoto, em segundos."""

    remote_pg_max_limit: int = 100
    """Limite máximo de registros retornados por consulta exploratória."""

    # ==========================================
    # Integrações Externas - Spring Boot
    # ==========================================
    remote_spring_base_url: str = "http://srv1428963.hstgr.cloud:8080"
    """URL base da API Spring Boot usada como backend de medições."""

    remote_spring_timeout_seconds: float = 15.0
    """Timeout padrão para chamadas à API Spring Boot."""

    remote_spring_username: str | None = None
    """E-mail de login da API Spring Boot (endpoint /api/auth/login)."""

    remote_spring_password: str | None = None
    """Senha de login da API Spring Boot (endpoint /api/auth/login)."""


# Instância global de configurações (singleton)
settings = Settings()
