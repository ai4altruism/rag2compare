"""Tests for LiteLLM provider usage capture."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.providers.llm.litellm import LiteLLMProvider, _extract_usage


def _usage_obj(**fields):
    """Build a SimpleNamespace mimicking the LiteLLM/Anthropic usage shape."""
    return SimpleNamespace(**fields)


class TestExtractUsage:
    def test_handles_none(self):
        assert _extract_usage(None) == {}

    def test_basic_token_counts(self):
        usage = _usage_obj(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert _extract_usage(usage) == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }

    def test_thinking_tokens_via_completion_tokens_details(self):
        usage = _usage_obj(
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=12_345),
        )
        result = _extract_usage(usage)
        assert result["thinking_tokens"] == 12_345
        assert result["prompt_tokens"] == 100

    def test_missing_fields_are_skipped(self):
        usage = _usage_obj(prompt_tokens=5)
        result = _extract_usage(usage)
        assert result == {"prompt_tokens": 5}


class TestLiteLLMProvider:
    @pytest.mark.asyncio
    async def test_generate_records_last_usage(self):
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))],
            usage=_usage_obj(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=7),
            ),
        )
        provider = LiteLLMProvider(model="anthropic/claude-opus-4-7")

        with patch(
            "src.providers.llm.litellm.litellm.acompletion",
            new=AsyncMock(return_value=fake_response),
        ):
            result = await provider.generate(
                [{"role": "user", "content": "hi"}],
                temperature=1.0,
                thinking={"type": "enabled", "budget_tokens": 32_000},
            )

        assert result == "hi"
        assert provider.last_usage == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "thinking_tokens": 7,
        }

    @pytest.mark.asyncio
    async def test_generate_passes_thinking_and_temperature_through(self):
        captured: dict = {}
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=None,
        )

        async def fake_acompletion(**kwargs):
            captured.update(kwargs)
            return fake_response

        provider = LiteLLMProvider(model="anthropic/claude-opus-4-7")
        with patch(
            "src.providers.llm.litellm.litellm.acompletion",
            new=fake_acompletion,
        ):
            await provider.generate(
                [{"role": "user", "content": "hi"}],
                temperature=1.0,
                thinking={"type": "enabled", "budget_tokens": 32_000},
            )

        assert captured["temperature"] == 1.0
        assert captured["thinking"] == {"type": "enabled", "budget_tokens": 32_000}
        assert captured["model"] == "anthropic/claude-opus-4-7"
