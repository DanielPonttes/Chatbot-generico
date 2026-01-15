"""
Testes para os endpoints da API.

Testa:
- GET /health
- POST /chat (com mock do provider)
- Manutenção de sessão
"""

import pytest


class TestHealthEndpoint:
    """Testes para o endpoint /health."""
    
    def test_health_returns_200(self, client, patched_services):
        """
        /health deve retornar status 200 quando provider está disponível.
        """
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["provider"] == "ollama"
        assert data["model"] == "test-model"
        assert data["provider_available"] is True
    
    def test_health_shows_degraded_when_provider_unavailable(
        self, client, patched_services
    ):
        """
        /health deve retornar status 'degraded' quando provider não responde.
        """
        # Configura mock para retornar indisponível
        patched_services["provider"].is_available.return_value = False
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "degraded"
        assert data["provider_available"] is False


class TestChatEndpoint:
    """Testes para o endpoint /chat."""
    
    def test_chat_returns_valid_response(self, client, patched_services):
        """
        /chat deve retornar resposta válida com session_id e reply.
        """
        response = client.post(
            "/chat",
            json={
                "session_id": "test-session-001",
                "message": "Olá, como você está?",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["session_id"] == "test-session-001"
        assert data["reply"] == "Esta é uma resposta de teste do chatbot."
        assert data["provider"] == "ollama"
        assert data["model"] == "test-model"
    
    def test_chat_saves_messages_to_memory(self, client, patched_services):
        """
        /chat deve salvar mensagem do usuário e resposta no histórico.
        """
        client.post(
            "/chat",
            json={
                "session_id": "test-memory-001",
                "message": "Mensagem de teste",
            },
        )
        
        memory = patched_services["memory"]
        
        # Verifica que add_message foi chamado duas vezes (user + assistant)
        assert memory.add_message.call_count == 2
        
        # Primeira chamada: mensagem do usuário
        first_call = memory.add_message.call_args_list[0]
        assert first_call[0] == ("test-memory-001", "user", "Mensagem de teste")
        
        # Segunda chamada: resposta do assistente
        second_call = memory.add_message.call_args_list[1]
        assert second_call[0][0] == "test-memory-001"
        assert second_call[0][1] == "assistant"
    
    def test_chat_retrieves_history_before_generating(self, client, patched_services):
        """
        /chat deve recuperar histórico antes de chamar o provider.
        """
        client.post(
            "/chat",
            json={
                "session_id": "test-history-001",
                "message": "Nova mensagem",
            },
        )
        
        memory = patched_services["memory"]
        provider = patched_services["provider"]
        
        # Verifica que get_formatted_history foi chamado
        memory.get_formatted_history.assert_called_with("test-history-001")
        
        # Verifica que generate foi chamado
        provider.generate.assert_called_once()
    
    def test_chat_validates_empty_session_id(self, client, patched_services):
        """
        /chat deve rejeitar session_id vazio.
        """
        response = client.post(
            "/chat",
            json={
                "session_id": "",
                "message": "Mensagem válida",
            },
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_chat_validates_empty_message(self, client, patched_services):
        """
        /chat deve rejeitar mensagem vazia.
        """
        response = client.post(
            "/chat",
            json={
                "session_id": "valid-session",
                "message": "",
            },
        )
        
        assert response.status_code == 422  # Validation error


class TestRootEndpoint:
    """Testes para o endpoint raiz /."""
    
    def test_root_returns_welcome_message(self, client):
        """
        / deve retornar mensagem de boas-vindas com links úteis.
        """
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "docs" in data
        assert data["docs"] == "/docs"
