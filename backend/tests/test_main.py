"""Unit tests for the AI Chatbot FastAPI backend.

Azure OpenAI is mocked via FastAPI dependency overrides — no real credentials needed.
"""
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import BadRequestError, InternalServerError, RateLimitError

from main import app, get_openai_client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completion(content: str = "Hello!", model: str = "gpt-4o") -> MagicMock:
    """Build a mock chat completion response."""
    mock = MagicMock()
    mock.choices[0].message.content = content
    mock.model = model
    mock.usage.total_tokens = 42
    return mock


def _make_status_error(cls, status_code: int) -> Exception:
    """Construct an openai APIStatusError subclass with a fake httpx response."""
    req = httpx.Request("POST", "https://test.openai.azure.com/")
    resp = httpx.Response(status_code, request=req)
    return cls("error", response=resp, body=None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def api_client(mock_client):
    """Test client with the Azure OpenAI dependency replaced by a mock."""
    app.dependency_overrides[get_openai_client] = lambda: mock_client
    with TestClient(app) as client:
        yield client, mock_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_check_returns_ok(api_client):
    client, _ = api_client
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Successful chat
# ---------------------------------------------------------------------------

def test_chat_returns_reply(api_client):
    client, mock = api_client
    mock.chat.completions.create.return_value = _make_completion("Hi there!")

    response = client.post("/chat", json={"messages": [{"role": "user", "content": "Hello"}]})

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Hi there!"
    assert data["model"] == "gpt-4o"


def test_chat_passes_all_messages_to_openai(api_client):
    client, mock = api_client
    mock.chat.completions.create.return_value = _make_completion("Sure!")

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
    ]
    client.post("/chat", json={"messages": messages})

    call_args = mock.chat.completions.create.call_args
    assert len(call_args.kwargs["messages"]) == 2
    assert call_args.kwargs["messages"][0]["role"] == "system"


def test_chat_respects_max_tokens(api_client):
    client, mock = api_client
    mock.chat.completions.create.return_value = _make_completion()

    client.post("/chat", json={"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 200})

    assert mock.chat.completions.create.call_args.kwargs["max_tokens"] == 200


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_rate_limit_returns_429(api_client):
    client, mock = api_client
    mock.chat.completions.create.side_effect = _make_status_error(RateLimitError, 429)

    response = client.post("/chat", json={"messages": [{"role": "user", "content": "Hi"}]})

    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"].lower()


def test_bad_request_returns_400(api_client):
    client, mock = api_client
    mock.chat.completions.create.side_effect = _make_status_error(BadRequestError, 400)

    response = client.post("/chat", json={"messages": [{"role": "user", "content": "Hi"}]})

    assert response.status_code == 400


def test_internal_server_error_returns_502(api_client):
    client, mock = api_client
    mock.chat.completions.create.side_effect = _make_status_error(InternalServerError, 500)

    response = client.post("/chat", json={"messages": [{"role": "user", "content": "Hi"}]})

    assert response.status_code == 502


# ---------------------------------------------------------------------------
# Input validation (Pydantic / 422)
# ---------------------------------------------------------------------------

def test_invalid_role_returns_422(api_client):
    client, _ = api_client
    response = client.post("/chat", json={"messages": [{"role": "hacker", "content": "Hi"}]})
    assert response.status_code == 422


def test_empty_messages_returns_422(api_client):
    client, _ = api_client
    response = client.post("/chat", json={"messages": []})
    assert response.status_code == 422


def test_message_content_too_long_returns_422(api_client):
    client, _ = api_client
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "x" * 4001}]})
    assert response.status_code == 422


def test_max_tokens_out_of_range_returns_422(api_client):
    client, _ = api_client
    response = client.post(
        "/chat", json={"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 99999}
    )
    assert response.status_code == 422


def test_too_many_messages_returns_422(api_client):
    client, _ = api_client
    messages = [{"role": "user", "content": "Hi"}] * 51
    response = client.post("/chat", json={"messages": messages})
    assert response.status_code == 422
