"""Anthropic adaptive-thinking ("reasoning effort") helper.

For Claude Opus 4.7, manual extended thinking
(`thinking={"type": "enabled", "budget_tokens": N}`) is no longer
accepted — the API returns 400. The supported shape is adaptive
thinking, configured by:

    thinking      = {"type": "adaptive", "display": "summarized"}
    output_config = {"effort": "<tier>"}

where `<tier>` is `low | medium | high | xhigh | max`. `xhigh` is
specifically Opus 4.7's high-end tier, matching Claude Code's
`xhigh` preset; `max` is the absolute ceiling. The effort acts as
soft guidance — Claude decides per-request how much to think.

Notes:
- `display` defaults to `"omitted"` on Opus 4.7 (silent change from
  Opus 4.6's `"summarized"` default). We opt back into summarized
  output so callers and human reviewers can inspect reasoning
  traces. Billing is the same either way.
- "off" disables thinking by omitting the `thinking` block entirely.
  On Opus 4.7 this is the default; on older models a `disabled`
  thinking type is required, but we don't target those models for
  the answer-generation path.
- Manual thinking with `budget_tokens` is still functional on Sonnet
  4.5 / Sonnet 4.6 / Opus 4.6 (deprecated), but our enrichment path
  doesn't enable thinking at all so we don't carry that code.

See https://platform.claude.com/docs/en/docs/build-with-claude/adaptive-thinking
"""

from __future__ import annotations

REASONING_EFFORTS: tuple[str, ...] = ("off", "low", "medium", "high", "xhigh", "max")


def is_thinking_enabled(effort: str | None) -> bool:
    """True if `effort` should turn adaptive thinking on."""
    if not effort:
        return False
    return effort.lower() != "off"


def thinking_param(effort: str | None) -> dict | None:
    """Build the Anthropic `thinking` block for adaptive thinking.

    Returns None when thinking should be disabled, so callers can spread
    the result conditionally without sending an empty/disabled value.
    """
    if not is_thinking_enabled(effort):
        return None
    return {"type": "adaptive", "display": "summarized"}


def effort_param(effort: str | None) -> dict | None:
    """Build the Anthropic `output_config` block for adaptive thinking.

    The effort tier is soft guidance for how much thinking Claude
    allocates per-request. Returns None when thinking is off.

    Unknown tiers fall back to `high` (Anthropic's default) rather than
    silently disabling thinking — if a config typo happens at runtime,
    we'd rather over-think than under-think a research query.
    """
    if not is_thinking_enabled(effort):
        return None
    tier = (effort or "").lower()
    if tier not in {"low", "medium", "high", "xhigh", "max"}:
        tier = "high"
    return {"effort": tier}
