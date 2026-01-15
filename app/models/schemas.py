"""
Schemas Pydantic para validação de requests e responses.

Define os modelos de dados usados na API.
"""

from typing import Literal
from pydantic import BaseModel, Field


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
    provider: Literal["ollama", "huggingface"] = Field(
        ...,
        description="Provider LLM usado para gerar a resposta",
    )
    model: str = Field(
        ...,
        description="Nome do modelo usado para gerar a resposta",
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
