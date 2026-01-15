"""
Configurações e fixtures para testes pytest.

Os mocks são aplicados no módulo onde as funções são USADAS (app.api.routes),
não onde são definidas, seguindo a regra do Python para monkeypatching.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Import the modules where we need to patch
from app import api
from app.api import routes
from app.main import app


@pytest.fixture
def client():
    """Cliente de teste para a API FastAPI."""
    return TestClient(app)


@pytest.fixture
def mock_llm_provider():
    """
    Mock do provider LLM para testes.
    
    Retorna respostas fixas sem chamar LLM real.
    """
    provider = MagicMock()
    provider.name = "ollama"
    provider.model = "test-model"
    provider.generate = AsyncMock(return_value="Esta é uma resposta de teste do chatbot.")
    provider.is_available = AsyncMock(return_value=True)
    return provider


@pytest.fixture
def mock_memory_manager():
    """
    Mock do gerenciador de memória para testes.
    
    Mantém histórico em dict simples.
    """
    manager = MagicMock()
    manager._history = {}
    
    def add_message(session_id, role, content):
        if session_id not in manager._history:
            manager._history[session_id] = []
        manager._history[session_id].append({"role": role, "content": content})
    
    def get_formatted_history(session_id):
        return manager._history.get(session_id, [])
    
    manager.add_message = MagicMock(side_effect=add_message)
    manager.get_formatted_history = MagicMock(side_effect=get_formatted_history)
    
    return manager


@pytest.fixture
def patched_services(mock_llm_provider, mock_memory_manager, monkeypatch):
    """
    Aplica mocks nos serviços para testes isolados.
    
    IMPORTANTE: Patches são aplicados no módulo routes onde as funções são chamadas,
    não nos módulos onde são definidas.
    """
    # Patch at the location where the functions are CALLED (app.api.routes)
    monkeypatch.setattr(routes, "get_llm_provider", lambda: mock_llm_provider)
    monkeypatch.setattr(routes, "get_memory_manager", lambda: mock_memory_manager)
    
    yield {
        "provider": mock_llm_provider,
        "memory": mock_memory_manager,
    }
