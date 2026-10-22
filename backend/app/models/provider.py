"""Abstract Model Provider interface for LLM completions.

Architecture decision (ADR-0001):
- AURA runs entirely on local open-weight models (Ollama / llama.cpp).
- This abstract base class defines the provider contract.
- The ``MockModelProvider`` allows unit tests to run at zero cost and
  zero infrastructure — tests never hit a real LLM.
- Production code should only depend on ``BaseModelProvider``; the
  concrete implementation is injected via the ``get_model_provider``
  FastAPI dependency which reads ``settings.MODEL_PROVIDER``.

Adding a new provider:
1. Subclass ``BaseModelProvider``.
2. Implement ``complete()``.
3. Register it in ``get_model_provider()``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("aura.models.provider")


# ---------------------------------------------------------------------------
# Shared data types
# ---------------------------------------------------------------------------


@dataclass
class ChatMessage:
    """A single turn in a chat conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionRequest:
    """Input to a model provider completion call."""

    messages: list[ChatMessage]
    model: str = ""
    max_tokens: int = 1024
    temperature: float = 0.7
    stop: list[str] = field(default_factory=list)


@dataclass
class CompletionResponse:
    """Output from a model provider completion call."""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseModelProvider(ABC):
    """Abstract contract for LLM completion providers.

    All concrete implementations MUST be safe to call from async context.
    """

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion for the given messages.

        Args:
            request: Structured completion request with messages and parameters.

        Returns:
            CompletionResponse with generated text and token counts.

        Raises:
            ModelProviderError: On any provider-level failure.
        """

    async def health_check(self) -> bool:
        """Return True if the provider is reachable and operational.

        Override in concrete implementations for real connectivity checks.
        """
        return True


class ModelProviderError(Exception):
    """Raised when a model provider encounters an unrecoverable error."""


# ---------------------------------------------------------------------------
# Mock Provider — zero-cost unit testing
# ---------------------------------------------------------------------------


class MockModelProvider(BaseModelProvider):
    """Deterministic stub provider for unit and integration tests.

    Returns configurable fixed responses without any network or GPU calls.
    """

    def __init__(self, fixed_response: str = "Mock response from AURA.") -> None:
        self._fixed_response = fixed_response
        self._call_count = 0
        logger.info("MockModelProvider initialized (test mode)")

    @property
    def call_count(self) -> int:
        """Number of times ``complete()`` has been called (useful in test assertions)."""
        return self._call_count

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return the fixed response without any network call."""
        self._call_count += 1
        logger.debug(
            "MockModelProvider.complete called (call #%d) with %d messages",
            self._call_count,
            len(request.messages),
        )
        return CompletionResponse(
            content=self._fixed_response,
            model="mock-model",
            prompt_tokens=sum(len(m.content.split()) for m in request.messages),
            completion_tokens=len(self._fixed_response.split()),
            finish_reason="stop",
        )

    async def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Ollama Provider (stub — wired in Phase 6)
# ---------------------------------------------------------------------------


class OllamaModelProvider(BaseModelProvider):
    """Ollama HTTP API provider (wired fully in Phase 6).

    Placeholder stub so imports resolve before Phase 6 implementation.
    """

    def __init__(self, base_url: str, model_name: str) -> None:
        self._base_url = base_url
        self._model_name = model_name
        logger.info("OllamaModelProvider initialized base_url=%s model=%s", base_url, model_name)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Stub: raises NotImplementedError until Phase 6."""
        raise NotImplementedError("OllamaModelProvider is implemented in Phase 6")


# ---------------------------------------------------------------------------
# Gemini Provider (Google AI Studio / Vertex)
# ---------------------------------------------------------------------------


class GeminiModelProvider(BaseModelProvider):
    """Google Gemini completion provider using v1beta REST API."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        self._api_key = api_key
        self._model_name = model_name.replace("models/", "")
        logger.info("GeminiModelProvider initialized with model=%s", self._model_name)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        import httpx

        contents = []
        system_instruction = None

        for msg in request.messages:
            if msg.role == "system":
                system_instruction = {"parts": [{"text": msg.content}]}
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg.content}]})

        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Hello"}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        model = (request.model or self._model_name).replace("models/", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self._api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                data = res.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise ModelProviderError(f"No candidates returned from Gemini: {data}")

                parts = candidates[0].get("content", {}).get("parts", [])
                text_content = "".join(p.get("text", "") for p in parts)
                usage = data.get("usageMetadata", {})
                prompt_tokens = usage.get("promptTokenCount", 0)
                completion_tokens = usage.get("candidatesTokenCount", 0)

                return CompletionResponse(
                    content=text_content,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    finish_reason=candidates[0].get("finishReason", "stop"),
                )
            except Exception as e:
                logger.error("Gemini API call failed: %s", e)
                raise ModelProviderError(f"Gemini API failure: {e}") from e

    async def health_check(self) -> bool:
        return bool(self._api_key)


# ---------------------------------------------------------------------------
# Provider factory — FastAPI dependency
# ---------------------------------------------------------------------------


def get_model_provider() -> BaseModelProvider:
    """Return the configured model provider based on ``settings.MODEL_PROVIDER``.

    Usage in endpoint:
        provider: BaseModelProvider = Depends(get_model_provider)
    """
    from backend.app.core.config import get_settings  # Lazy import avoids circular

    settings = get_settings()
    if settings.MODEL_PROVIDER == "mock":
        return MockModelProvider()
    if settings.MODEL_PROVIDER == "gemini":
        api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else ""
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be configured when MODEL_PROVIDER='gemini'")
        return GeminiModelProvider(
            api_key=api_key,
            model_name=settings.MODEL_NAME or "gemini-2.5-flash",
        )
    if settings.MODEL_PROVIDER == "ollama":
        return OllamaModelProvider(
            base_url=settings.MODEL_BASE_URL,
            model_name=settings.MODEL_NAME,
        )
    raise ValueError(f"Unknown MODEL_PROVIDER: {settings.MODEL_PROVIDER!r}")


__all__ = [
    "BaseModelProvider",
    "ChatMessage",
    "CompletionRequest",
    "CompletionResponse",
    "GeminiModelProvider",
    "MockModelProvider",
    "ModelProviderError",
    "OllamaModelProvider",
    "get_model_provider",
]
