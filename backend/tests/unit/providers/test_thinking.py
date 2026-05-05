"""Tests for the adaptive-thinking helpers."""

from src.providers.llm.thinking import (
    REASONING_EFFORTS,
    effort_param,
    is_thinking_enabled,
    thinking_param,
)


class TestIsThinkingEnabled:
    def test_off_is_disabled(self):
        assert is_thinking_enabled("off") is False

    def test_none_is_disabled(self):
        assert is_thinking_enabled(None) is False

    def test_empty_string_is_disabled(self):
        assert is_thinking_enabled("") is False

    def test_xhigh_is_enabled(self):
        assert is_thinking_enabled("xhigh") is True

    def test_max_is_enabled(self):
        assert is_thinking_enabled("max") is True

    def test_low_is_enabled(self):
        assert is_thinking_enabled("low") is True

    def test_case_insensitive(self):
        assert is_thinking_enabled("XHIGH") is True


class TestThinkingParam:
    def test_off_returns_none(self):
        assert thinking_param("off") is None

    def test_none_returns_none(self):
        assert thinking_param(None) is None

    def test_xhigh_returns_adaptive_summarized(self):
        # Critical: must be type=adaptive (not enabled), and display=summarized
        # to opt into reasoning trace on Opus 4.7 (which silently flipped
        # the default to omitted).
        assert thinking_param("xhigh") == {
            "type": "adaptive",
            "display": "summarized",
        }

    def test_max_returns_adaptive_summarized(self):
        assert thinking_param("max") == {
            "type": "adaptive",
            "display": "summarized",
        }

    def test_low_returns_adaptive_summarized(self):
        assert thinking_param("low") == {
            "type": "adaptive",
            "display": "summarized",
        }

    def test_no_budget_tokens_anywhere(self):
        # Regression: budget_tokens is rejected with 400 on Opus 4.7 — make
        # sure no codepath ever emits it.
        for effort in REASONING_EFFORTS:
            block = thinking_param(effort)
            if block is not None:
                assert "budget_tokens" not in block
                assert block.get("type") != "enabled"


class TestEffortParam:
    def test_off_returns_none(self):
        assert effort_param("off") is None

    def test_xhigh_returns_effort_block(self):
        assert effort_param("xhigh") == {"effort": "xhigh"}

    def test_max_returns_effort_block(self):
        assert effort_param("max") == {"effort": "max"}

    def test_high_returns_effort_block(self):
        assert effort_param("high") == {"effort": "high"}

    def test_unknown_tier_falls_back_to_high(self):
        # Defensive: a config typo should over-think rather than silently
        # disable thinking on a research query.
        assert effort_param("xtreme") == {"effort": "high"}

    def test_case_insensitive(self):
        assert effort_param("XHigh") == {"effort": "xhigh"}


class TestEffortsList:
    def test_includes_max(self):
        # The Opus 4.7 effort tiers are low/medium/high/xhigh/max plus our
        # synthetic "off". `max` was added in v1.1 — keep it in the list.
        assert "max" in REASONING_EFFORTS

    def test_includes_off(self):
        assert "off" in REASONING_EFFORTS
