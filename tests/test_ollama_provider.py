"""Testes do provider Ollama local e remoto com Basic Auth."""

import base64
import logging

import httpx
import pytest

import app.services.llm_provider as llm_provider_module
from app.services.llm_provider import OllamaProvider, ProviderNotAvailableError


async def _client_with_transport(provider: OllamaProvider, handler) -> None:
    """Troca o transporte real por MockTransport mantendo a autenticação."""
    await provider._client.aclose()
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        auth=provider._auth,
    )


@pytest.mark.asyncio
async def test_basic_auth_is_sent_to_tags_and_chat():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gemma4:26b"}]})
        return httpx.Response(200, json={"message": {"content": "OK"}})

    provider = OllamaProvider(
        base_url="https://ollama.example",
        model_name="gemma4:26b",
        username="proxy-user",
        password="proxy-pass",
    )
    await _client_with_transport(provider, handler)

    try:
        assert await provider.is_available() is True
        assert await provider.generate("Responda somente OK") == "OK"
    finally:
        await provider.close()

    expected = "Basic " + base64.b64encode(b"proxy-user:proxy-pass").decode()
    assert len(requests) == 2
    assert all(request.headers["authorization"] == expected for request in requests)


@pytest.mark.asyncio
async def test_local_ollama_without_credentials_sends_no_auth_header():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"models": [{"name": "gemma4:26b"}]})

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model_name="gemma4:26b",
    )
    await _client_with_transport(provider, handler)

    try:
        assert await provider.is_available() is True
    finally:
        await provider.close()

    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize("username, password", [("proxy-user", None), ("proxy-user", " ")])
def test_ollama_credentials_must_be_configured_together(username, password):
    with pytest.raises(ValueError, match="configurados juntos"):
        OllamaProvider(
            base_url="https://ollama.example",
            username=username,
            password=password,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_ollama_auth_failure_becomes_provider_unavailable_error(status_code):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    provider = OllamaProvider(
        base_url="https://ollama.example",
        model_name="gemma4:26b",
        username="proxy-user",
        password="wrong-pass",
    )
    await _client_with_transport(provider, handler)

    try:
        with pytest.raises(ProviderNotAvailableError, match="autenticação"):
            await provider.generate("Olá")
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_ollama_health_logs_auth_failure(caplog, status_code):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    provider = OllamaProvider(
        base_url="https://ollama.example",
        model_name="gemma4:26b",
        username="proxy-user",
        password="proxy-pass",
    )
    await _client_with_transport(provider, handler)

    try:
        with caplog.at_level(logging.WARNING, logger="app.services.llm_provider"):
            assert await provider.is_available() is False
    finally:
        await provider.close()

    assert f"HTTP {status_code}" in caplog.text
    assert "proxy-pass" not in caplog.text


@pytest.mark.asyncio
async def test_ollama_provider_reads_credentials_from_settings(monkeypatch):
    monkeypatch.setattr(llm_provider_module.settings, "ollama_base_url", "https://ollama.example")
    monkeypatch.setattr(llm_provider_module.settings, "ollama_model", "gemma4:26b")
    monkeypatch.setattr(llm_provider_module.settings, "ollama_username", "settings-user")
    monkeypatch.setattr(llm_provider_module.settings, "ollama_password", "settings-pass")

    provider = OllamaProvider()
    try:
        assert provider.model == "gemma4:26b"
        assert provider._auth is not None
    finally:
        await provider.close()
