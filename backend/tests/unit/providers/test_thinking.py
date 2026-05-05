"""Tests for the reasoning-effort → thinking-budget mapping helper."""

from src.providers.llm.thinking import budget_for, thinking_param


class TestBudgetFor:
    def test_off_returns_zero(self):
        assert budget_for("off") == 0

    def test_xhigh_is_32000(self):
        assert budget_for("xhigh") == 32_000

    def test_high_is_16384(self):
        assert budget_for("high") == 16_384

    def test_unknown_falls_back_to_zero(self):
        assert budget_for("xtreme") == 0

    def test_none_falls_back_to_zero(self):
        assert budget_for(None) == 0

    def test_empty_string_falls_back_to_zero(self):
        assert budget_for("") == 0

    def test_case_insensitive(self):
        assert budget_for("XHIGH") == 32_000
        assert budget_for("XHigh") == 32_000


class TestThinkingParam:
    def test_off_returns_none(self):
        assert thinking_param("off") is None

    def test_none_returns_none(self):
        assert thinking_param(None) is None

    def test_xhigh_returns_anthropic_dict(self):
        assert thinking_param("xhigh") == {"type": "enabled", "budget_tokens": 32_000}

    def test_low_returns_4k(self):
        assert thinking_param("low") == {"type": "enabled", "budget_tokens": 4_096}
