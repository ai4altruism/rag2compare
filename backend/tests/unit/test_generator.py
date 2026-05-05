"""Tests for answer generator."""

from unittest.mock import AsyncMock

import pytest

from src.pipelines.query.generator import AnswerGenerator
from src.storage.qdrant import SearchResult


def _make_chunk(id_: str, score: float, text: str = "chunk text",
                filename: str = "doc.pdf", pages: list[int] | None = None) -> SearchResult:
    return SearchResult(
        id=id_,
        score=score,
        payload={
            "chunk_text": text,
            "document_id": "d1",
            "filename": filename,
            "page_numbers": pages or [1],
            "header_chain": ["Section 1"],
        },
    )


@pytest.fixture
def mock_llm():
    mock = AsyncMock()
    mock.model_name = "test-model"
    mock.generate.return_value = "Based on the context, the answer is 42. [Source 1]"
    return mock


class TestAnswerGenerator:
    async def test_generate_returns_answer_and_citations(self, mock_llm):
        gen = AnswerGenerator(mock_llm)
        chunks = [_make_chunk("c1", 0.9, "The answer is 42")]

        result = await gen.generate("What is the answer?", chunks)

        assert "42" in result.answer
        assert len(result.citations) == 1
        assert result.citations[0].index == 1
        assert result.citations[0].filename == "doc.pdf"

    async def test_generate_passes_system_prompt(self, mock_llm):
        gen = AnswerGenerator(mock_llm)
        await gen.generate("q", [_make_chunk("c1", 0.9)])

        messages = mock_llm.generate.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert "ONLY" in messages[0]["content"]

    async def test_generate_custom_system_prompt(self, mock_llm):
        gen = AnswerGenerator(mock_llm, system_prompt="You are a summarizer.")
        await gen.generate("q", [_make_chunk("c1", 0.9)])

        messages = mock_llm.generate.call_args[0][0]
        assert messages[0]["content"] == "You are a summarizer."

    async def test_generate_includes_context_in_message(self, mock_llm):
        gen = AnswerGenerator(mock_llm)
        chunks = [
            _make_chunk("c1", 0.9, "First chunk"),
            _make_chunk("c2", 0.8, "Second chunk", filename="other.pdf", pages=[3, 4]),
        ]

        await gen.generate("question?", chunks)

        messages = mock_llm.generate.call_args[0][0]
        user_msg = messages[-1]["content"]
        assert "[Source 1]" in user_msg
        assert "[Source 2]" in user_msg
        assert "First chunk" in user_msg
        assert "Second chunk" in user_msg
        assert "other.pdf" in user_msg
        assert "question?" in user_msg

    async def test_generate_with_conversation_history(self, mock_llm):
        gen = AnswerGenerator(mock_llm)
        history = [
            {"role": "user", "content": "What is X?"},
            {"role": "assistant", "content": "X is Y."},
        ]

        await gen.generate("Follow up", [_make_chunk("c1", 0.9)], conversation_history=history)

        messages = mock_llm.generate.call_args[0][0]
        # system + 2 history + 1 user = 4
        assert len(messages) == 4
        assert messages[1]["content"] == "What is X?"
        assert messages[2]["content"] == "X is Y."

    async def test_citations_preserve_scores(self, mock_llm):
        gen = AnswerGenerator(mock_llm)
        chunks = [
            _make_chunk("c1", 0.95),
            _make_chunk("c2", 0.82),
        ]

        result = await gen.generate("q", chunks)

        assert result.citations[0].relevance_score == 0.95
        assert result.citations[1].relevance_score == 0.82
        assert result.citations[0].index == 1
        assert result.citations[1].index == 2

    async def test_generate_uses_low_temperature_by_default(self, mock_llm):
        gen = AnswerGenerator(mock_llm)
        await gen.generate("q", [_make_chunk("c1", 0.9)])

        kwargs = mock_llm.generate.call_args[1]
        assert kwargs["temperature"] == 0.2
        assert "thinking" not in kwargs
        assert "output_config" not in kwargs

    async def test_generate_with_xhigh_passes_adaptive_thinking_plus_effort(self, mock_llm):
        gen = AnswerGenerator(mock_llm, reasoning_effort="xhigh")
        await gen.generate("q", [_make_chunk("c1", 0.9)])

        kwargs = mock_llm.generate.call_args[1]
        # Adaptive thinking — manual budget_tokens 400s on Opus 4.7.
        assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
        # Effort tier is its own top-level field, separate from thinking.
        assert kwargs["output_config"] == {"effort": "xhigh"}
        # Temperature stays at 1.0 — historical thinking constraint, harmless default.
        assert kwargs["temperature"] == 1.0
        # max_tokens generous so xhigh thinking doesn't get truncated.
        assert kwargs["max_tokens"] >= 16_000

    async def test_generate_with_max_passes_max_effort(self, mock_llm):
        gen = AnswerGenerator(mock_llm, reasoning_effort="max")
        await gen.generate("q", [_make_chunk("c1", 0.9)])

        kwargs = mock_llm.generate.call_args[1]
        assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert kwargs["output_config"] == {"effort": "max"}

    async def test_generate_never_emits_budget_tokens(self, mock_llm):
        # Regression: budget_tokens is rejected with 400 on Opus 4.7. The
        # generator must not emit it through any code path.
        for effort in (None, "off", "low", "medium", "high", "xhigh", "max"):
            gen = AnswerGenerator(mock_llm, reasoning_effort=effort)
            await gen.generate("q", [_make_chunk("c1", 0.9)])
            kwargs = mock_llm.generate.call_args[1]
            thinking = kwargs.get("thinking")
            if thinking is not None:
                assert thinking.get("type") != "enabled"
                assert "budget_tokens" not in thinking

    async def test_generate_with_off_thinking_keeps_low_temp(self, mock_llm):
        gen = AnswerGenerator(mock_llm, reasoning_effort="off", temperature=0.2)
        await gen.generate("q", [_make_chunk("c1", 0.9)])

        kwargs = mock_llm.generate.call_args[1]
        assert kwargs["temperature"] == 0.2
        assert "thinking" not in kwargs
        assert "output_config" not in kwargs
        assert "max_tokens" not in kwargs

    async def test_generate_stream_passes_include_usage_and_adaptive(self, mock_llm):
        captured: dict = {}

        async def mock_stream(messages, **kwargs):
            captured.update(kwargs)
            for token in ["a", "b"]:
                yield token

        mock_llm.generate_stream = mock_stream
        gen = AnswerGenerator(mock_llm, reasoning_effort="xhigh")
        async for _ in gen.generate_stream("q", [_make_chunk("c1", 0.9)]):
            pass

        assert captured["stream_options"] == {"include_usage": True}
        assert captured["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert captured["output_config"] == {"effort": "xhigh"}
        assert captured["temperature"] == 1.0
        assert captured["max_tokens"] >= 16_000

    async def test_generate_stream(self, mock_llm):
        async def mock_stream(*args, **kwargs):
            for token in ["The ", "answer ", "is ", "42."]:
                yield token

        mock_llm.generate_stream = mock_stream

        gen = AnswerGenerator(mock_llm)
        tokens = []
        async for token in gen.generate_stream("q", [_make_chunk("c1", 0.9)]):
            tokens.append(token)

        assert tokens == ["The ", "answer ", "is ", "42."]

    async def test_generate_empty_chunks(self, mock_llm):
        mock_llm.generate.return_value = "No context provided."
        gen = AnswerGenerator(mock_llm)

        result = await gen.generate("q", [])

        assert result.citations == []
        assert result.answer == "No context provided."
