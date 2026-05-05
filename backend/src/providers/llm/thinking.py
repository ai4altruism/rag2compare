"""Anthropic extended-thinking ("reasoning effort") helper.

Maps a human-readable effort level to a budget_tokens value for Anthropic's
`thinking` parameter. Used for Claude Opus 4.7 and other models that support
extended reasoning. When budget > 0 the LLM call must also use temperature=1.0.
"""

from __future__ import annotations

REASONING_EFFORTS = ("off", "low", "medium", "high", "xhigh")

_BUDGETS: dict[str, int] = {
    "off": 0,
    "low": 4_096,
    "medium": 8_192,
    "high": 16_384,
    "xhigh": 32_000,
}


def budget_for(effort: str | None) -> int:
    """Return the budget_tokens value for a given effort level.

    Unknown values fall back to "off" (no thinking). Returns 0 when thinking
    should be disabled.
    """
    if not effort:
        return 0
    return _BUDGETS.get(effort.lower(), 0)


def thinking_param(effort: str | None) -> dict | None:
    """Build the Anthropic `thinking` parameter for a given effort level.

    Returns None when thinking should be disabled, so callers can spread the
    result conditionally without sending an empty/disabled value.
    """
    budget = budget_for(effort)
    if budget <= 0:
        return None
    return {"type": "enabled", "budget_tokens": budget}
