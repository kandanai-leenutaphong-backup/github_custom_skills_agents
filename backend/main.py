"""
Azure OpenAI AI Chatbot — FastAPI backend.

Security: uses DefaultAzureCredential (managed identity / Entra ID) — no API keys.
"""
import logging
import os
from typing import Annotated

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import APIError, AzureOpenAI, BadRequestError, RateLimitError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=50)
    max_tokens: int = Field(default=800, ge=1, le=4096)


class ChatResponse(BaseModel):
    reply: str
    model: str


# ---------------------------------------------------------------------------
# Azure OpenAI client dependency
# ---------------------------------------------------------------------------

def _create_openai_client() -> AzureOpenAI:
    """Build an AzureOpenAI client backed by DefaultAzureCredential (no API keys)."""
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE)
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=api_version,
    )


def get_openai_client() -> AzureOpenAI:
    """FastAPI dependency: returns an Azure OpenAI client."""
    return _create_openai_client()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Chatbot API", version="1.0.0")

_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

def _map_openai_error(exc: Exception, deployment: str) -> HTTPException:
    """Convert OpenAI SDK errors to HTTP exceptions with safe user-facing messages."""
    if isinstance(exc, RateLimitError):
        logger.warning("Rate limit reached for deployment=%s", deployment)
        return HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a moment and try again.",
        )
    if isinstance(exc, BadRequestError):
        logger.warning("Bad request to Azure OpenAI deployment=%s: %s", deployment, exc.message)
        return HTTPException(status_code=400, detail=f"Invalid request: {exc.message}")
    if isinstance(exc, APIError):
        logger.error("Azure OpenAI API error deployment=%s: %s", deployment, exc)
        return HTTPException(
            status_code=502,
            detail="Azure OpenAI service error. Please try again later.",
        )
    logger.error("Unexpected error deployment=%s: %s", deployment, exc, exc_info=True)
    return HTTPException(status_code=500, detail="An unexpected error occurred.")


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client: Annotated[AzureOpenAI, Depends(get_openai_client)],
) -> ChatResponse:
    """Send a conversation to Azure OpenAI and return the assistant reply."""
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[m.model_dump() for m in request.messages],
            max_tokens=request.max_tokens,
        )
        reply = response.choices[0].message.content or ""
        usage = response.usage.total_tokens if response.usage else "N/A"
        logger.info("Chat succeeded model=%s total_tokens=%s", response.model, usage)
        return ChatResponse(reply=reply, model=response.model)
    except (RateLimitError, BadRequestError, APIError) as exc:
        raise _map_openai_error(exc, deployment) from exc
    except KeyError as exc:
        logger.error("Missing environment variable: %s", exc)
        raise HTTPException(status_code=500, detail="Server configuration error.") from exc
