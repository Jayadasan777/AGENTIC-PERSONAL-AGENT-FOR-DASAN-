"""Unit tests for the Mock Model Provider interface.

These tests run entirely in-memory — no database, no LLM, no network.
They verify the BaseModelProvider contract and MockModelProvider behaviour.
"""

from __future__ import annotations

import pytest

from backend.app.models.provider import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    MockModelProvider,
    OllamaModelProvider,
    get_model_provider,
)

# ---------------------------------------------------------------------------
# MockModelProvider
# ---------------------------------------------------------------------------


class TestMockModelProvider:
    @pytest.mark.asyncio
    async def test_returns_fixed_response(self) -> None:
        provider = MockModelProvider(fixed_response="Test answer")
        request = CompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")]
        )
        response = await provider.complete(request)
        assert response.content == "Test answer"

    @pytest.mark.asyncio
    async def test_response_has_correct_type(self) -> None:
        provider = MockModelProvider()
        request = CompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")]
        )
        response = await provider.complete(request)
        assert isinstance(response, CompletionResponse)

    @pytest.mark.asyncio
    async def test_call_count_increments(self) -> None:
        provider = MockModelProvider()
        request = CompletionRequest(
            messages=[ChatMessage(role="user", content="ping")]
        )
        assert provider.call_count == 0
        await provider.complete(request)
        await provider.complete(request)
        assert provider.call_count == 2

    @pytest.mark.asyncio
    async def test_model_name_is_mock(self) -> None:
        provider = MockModelProvider()
        request = CompletionRequest(
            messages=[ChatMessage(role="user", content="test")]
        )
        response = await provider.complete(request)
        assert response.model == "mock-model"

    @pytest.mark.asyncio
    async def test_health_check_returns_true(self) -> None:
        provider = MockModelProvider()
        assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_prompt_tokens_counted(self) -> None:
        provider = MockModelProvider()
        request = CompletionRequest(
            messages=[
                ChatMessage(role="system", content="You are helpful"),
                ChatMessage(role="user", content="Tell me a story"),
            ]
        )
        response = await provider.complete(request)
        # Prompt tokens = word count across all messages
        assert response.prompt_tokens > 0

    @pytest.mark.asyncio
    async def test_multiple_messages_handled(self) -> None:
        provider = MockModelProvider(fixed_response="OK")
        request = CompletionRequest(
            messages=[
                ChatMessage(role="system", content="System prompt"),
                ChatMessage(role="user", content="User message"),
                ChatMessage(role="assistant", content="Previous reply"),
                ChatMessage(role="user", content="Follow-up question"),
            ]
        )
        response = await provider.complete(request)
        assert response.content == "OK"
        assert response.finish_reason == "stop"


# ---------------------------------------------------------------------------
# OllamaModelProvider stub
# ---------------------------------------------------------------------------


class TestOllamaProviderStub:
    @pytest.mark.asyncio
    async def test_raises_not_implemented(self) -> None:
        provider = OllamaModelProvider(
            base_url="http://localhost:11434", model_name="llama3"
        )
        request = CompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")]
        )
        with pytest.raises(NotImplementedError):
            await provider.complete(request)


# ---------------------------------------------------------------------------
# Factory: get_model_provider
# ---------------------------------------------------------------------------


class TestGetModelProvider:
    def test_returns_mock_provider_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import backend.app.core.config as cfg_module

        # Clear the real lru_cache so get_settings is not called from cache
        cfg_module.get_settings.cache_clear()

        # Replace get_settings with a plain function returning mock-provider settings
        from backend.app.core.config import Settings

        monkeypatch.setattr(
            cfg_module,
            "get_settings",
            lambda: Settings(MODEL_PROVIDER="mock"),
        )

        provider = get_model_provider()
        assert isinstance(provider, MockModelProvider)

        # Restore: undo monkeypatch (handled by pytest teardown), clear real cache
        monkeypatch.undo()
        cfg_module.get_settings.cache_clear()

    def test_raises_on_unknown_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock

        import backend.app.core.config as cfg_module

        fake_settings = MagicMock()
        fake_settings.MODEL_PROVIDER = "nonexistent"
        monkeypatch.setattr(cfg_module, "get_settings", lambda: fake_settings)

        with pytest.raises(ValueError, match="Unknown MODEL_PROVIDER"):
            get_model_provider()
