"""Unit tests for the judge tooling — rubric, blinding, prompt, parsing, aggregation."""

import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts.judge_runs import (
    JUDGE_SYSTEM_PROMPT,
    SYSTEM_RAG,
    SYSTEM_WIKI,
    aggregate,
    blind,
    build_user_prompt,
    load_rubric,
    load_run,
    main,
    pair_runs,
    parse_judge_response,
    QuestionRecord,
    JudgmentResult,
    _extract_json_object,
    _coerce_scores,
    _inter_rater_deltas,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _rubric_yaml() -> dict:
    return {
        "criteria": [
            {
                "id": "groundedness",
                "label": "Groundedness",
                "description": "Are claims grounded?",
                "anchors": {"1": "no", "10": "yes"},
            },
            {
                "id": "structural_integrity",
                "label": "Structural Integrity",
                "description": "Is it cohesive?",
                "anchors": {"1": "disjoint", "10": "unified"},
            },
        ]
    }


@pytest.fixture
def rubric_path(tmp_path: Path) -> Path:
    p = tmp_path / "rubric.yaml"
    p.write_text(yaml.safe_dump(_rubric_yaml()))
    return p


def _run_payload(label: str) -> dict:
    return {
        "started_at": "20260504T210000Z",
        "results": [
            {
                "id": "q1",
                "tier": "multi-hop",
                "bias": "wiki",
                "text": "synthesize",
                "answer": f"answer from {label} for q1",
                "sources": [
                    {
                        "filename": f"{label}-paper.pdf",
                        "page_numbers": [3, 4],
                        "chunk_text": f"verbatim chunk from {label}",
                        "relevance_score": 0.81,
                    }
                ],
                "metadata": {"latency_ms": 1234},
            },
            {
                "id": "q2",
                "tier": "bias-check",
                "bias": "rag",
                "text": "exact stat?",
                "answer": f"answer from {label} for q2",
                "sources": [],
                "metadata": {"latency_ms": 999},
            },
        ],
    }


@pytest.fixture
def runs(tmp_path: Path) -> tuple[Path, Path]:
    rag_path = tmp_path / "rag-run.json"
    wiki_path = tmp_path / "wiki-run.json"
    rag_path.write_text(json.dumps(_run_payload("rag")))
    wiki_path.write_text(json.dumps(_run_payload("wiki")))
    return rag_path, wiki_path


@pytest.fixture
def question_record() -> QuestionRecord:
    return QuestionRecord(
        id="q1",
        tier="multi-hop",
        bias="wiki",
        text="What's the relationship?",
        rag_answer="answer from rag for q1",
        rag_sources=[
            {
                "filename": "rag-paper.pdf",
                "page_numbers": [3],
                "chunk_text": "rag chunk text",
                "relevance_score": 0.7,
            }
        ],
        rag_metadata={"latency_ms": 1234},
        wiki_answer="answer from wiki for q1",
        wiki_sources=[
            {
                "filename": "wiki-page.md",
                "page_numbers": [],
                "chunk_text": "wiki chunk text",
                "relevance_score": 0.92,
            }
        ],
        wiki_metadata={"latency_ms": 500},
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoadRubric:
    def test_parses_criteria(self, rubric_path: Path):
        rubric = load_rubric(rubric_path)
        assert rubric.ids == ["groundedness", "structural_integrity"]
        assert rubric.criteria[0].label == "Groundedness"
        assert rubric.criteria[0].anchors["1"] == "no"

    def test_missing_criteria_key_raises(self, tmp_path: Path):
        p = tmp_path / "bad.yaml"
        p.write_text("foo: bar\n")
        with pytest.raises(ValueError, match="missing 'criteria:'"):
            load_rubric(p)

    def test_empty_criteria_raises(self, tmp_path: Path):
        p = tmp_path / "empty.yaml"
        p.write_text(yaml.safe_dump({"criteria": []}))
        with pytest.raises(ValueError, match="no criteria"):
            load_rubric(p)


class TestLoadRun:
    def test_parses(self, runs: tuple[Path, Path]):
        rag_path, _ = runs
        data = load_run(rag_path)
        assert "results" in data
        assert len(data["results"]) == 2

    def test_missing_results_raises(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{}")
        with pytest.raises(ValueError, match="missing 'results:'"):
            load_run(p)


class TestPairRuns:
    def test_matches_by_id(self, runs: tuple[Path, Path]):
        rag, wiki = (load_run(p) for p in runs)
        pairs = pair_runs(rag, wiki)
        ids = [p.id for p in pairs]
        assert ids == ["q1", "q2"]

    def test_skips_unmatched(self, capsys):
        rag = {"results": [{"id": "q1", "answer": "a"}, {"id": "q3", "answer": "c"}]}
        wiki = {"results": [{"id": "q1", "answer": "x"}, {"id": "q2", "answer": "y"}]}
        pairs = pair_runs(rag, wiki)
        assert [p.id for p in pairs] == ["q1"]
        out = capsys.readouterr().out
        assert "q3" in out  # warning about RAG-only
        assert "q2" in out  # warning about Wiki-only


# ---------------------------------------------------------------------------
# Blinding
# ---------------------------------------------------------------------------


class TestBlinding:
    def test_deterministic_with_seed(self):
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        ids = ["q1", "q2", "q3", "q4"]
        b1 = [blind(rng1, qid) for qid in ids]
        b2 = [blind(rng2, qid) for qid in ids]
        assert b1 == b2

    def test_returns_complementary_assignment(self):
        rng = random.Random(0)
        for _ in range(20):
            b = blind(rng, "q")
            assert sorted([b["A"], b["B"]]) == sorted([SYSTEM_RAG, SYSTEM_WIKI])

    def test_balanced_over_many_calls(self):
        rng = random.Random(1234)
        a_is_rag = sum(1 for _ in range(2000) if blind(rng, "q")["A"] == SYSTEM_RAG)
        # Within ~3 sigma of 1000 with N=2000 binomial.
        assert 900 <= a_is_rag <= 1100


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


class TestPromptAssembly:
    def test_orders_systems_by_blinding_label(self, question_record, rubric_path):
        rubric = load_rubric(rubric_path)
        # Force A=wiki, B=rag — answers must appear in that order in the prompt.
        prompt = build_user_prompt(
            question_record, {"A": SYSTEM_WIKI, "B": SYSTEM_RAG}, rubric
        )
        a_idx = prompt.find("answer from wiki for q1")
        b_idx = prompt.find("answer from rag for q1")
        assert 0 <= a_idx < b_idx, f"A must precede B; got A={a_idx}, B={b_idx}"

    def test_includes_rubric_anchors(self, question_record, rubric_path):
        rubric = load_rubric(rubric_path)
        prompt = build_user_prompt(
            question_record, {"A": SYSTEM_RAG, "B": SYSTEM_WIKI}, rubric
        )
        assert "Groundedness" in prompt
        assert "no" in prompt  # the "1" anchor
        assert "yes" in prompt  # the "10" anchor

    def test_includes_question_text_and_tier(self, question_record, rubric_path):
        rubric = load_rubric(rubric_path)
        prompt = build_user_prompt(
            question_record, {"A": SYSTEM_RAG, "B": SYSTEM_WIKI}, rubric
        )
        assert "What's the relationship?" in prompt
        assert "multi-hop" in prompt

    def test_includes_sources_with_pages_and_scores(self, question_record, rubric_path):
        rubric = load_rubric(rubric_path)
        prompt = build_user_prompt(
            question_record, {"A": SYSTEM_RAG, "B": SYSTEM_WIKI}, rubric
        )
        assert "rag-paper.pdf" in prompt
        assert "p. 3" in prompt
        assert "0.700" in prompt or "0.7" in prompt

    def test_handles_empty_sources(self, rubric_path):
        rubric = load_rubric(rubric_path)
        record = QuestionRecord(
            id="q",
            tier="t",
            bias="b",
            text="text",
            rag_answer="r",
            rag_sources=[],
            rag_metadata={},
            wiki_answer="w",
            wiki_sources=[],
            wiki_metadata={},
        )
        prompt = build_user_prompt(record, {"A": SYSTEM_RAG, "B": SYSTEM_WIKI}, rubric)
        assert "no sources retrieved" in prompt

    def test_system_prompt_demands_json_only(self):
        assert "JSON object" in JUDGE_SYSTEM_PROMPT
        assert "system_a" in JUDGE_SYSTEM_PROMPT
        assert "system_b" in JUDGE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------


class TestExtractJsonObject:
    def test_pure_json(self):
        assert _extract_json_object('{"a": 1}') == {"a": 1}

    def test_json_with_prose_around(self):
        text = 'Sure, here you go:\n```json\n{"a": 1}\n```\nThanks!'
        assert _extract_json_object(text) == {"a": 1}

    def test_handles_nested_braces(self):
        text = 'prefix {"a": {"b": 2}} suffix'
        assert _extract_json_object(text) == {"a": {"b": 2}}

    def test_returns_none_on_garbage(self):
        assert _extract_json_object("nothing here") is None

    def test_returns_none_on_invalid_json(self):
        assert _extract_json_object("{not valid}") is None


class TestCoerceScores:
    def test_valid_ints(self):
        assert _coerce_scores({"g": 7, "s": 4}, ["g", "s"]) == {"g": 7, "s": 4}

    def test_missing_keys_become_none(self):
        assert _coerce_scores({"g": 7}, ["g", "s"]) == {"g": 7, "s": None}

    def test_out_of_range_becomes_none(self):
        assert _coerce_scores({"g": 11, "s": 0}, ["g", "s"]) == {"g": None, "s": None}

    def test_floats_with_integer_values_accepted(self):
        assert _coerce_scores({"g": 7.0}, ["g"]) == {"g": 7}

    def test_strings_rejected(self):
        assert _coerce_scores({"g": "7"}, ["g"]) == {"g": None}

    def test_booleans_rejected(self):
        assert _coerce_scores({"g": True}, ["g"]) == {"g": None}


class TestParseJudgeResponse:
    def test_well_formed_response(self):
        raw = json.dumps(
            {
                "system_a": {"groundedness": 8, "structural_integrity": 7},
                "system_b": {"groundedness": 5, "structural_integrity": 9},
                "notes": "A is grounded better; B is more cohesive.",
            }
        )
        a, b, notes, error = parse_judge_response(
            raw, ["groundedness", "structural_integrity"]
        )
        assert a == {"groundedness": 8, "structural_integrity": 7}
        assert b == {"groundedness": 5, "structural_integrity": 9}
        assert "grounded better" in notes
        assert error is None

    def test_garbage_response_yields_error(self):
        a, b, notes, error = parse_judge_response("nothing here", ["g"])
        assert a == {"g": None}
        assert b == {"g": None}
        assert error is not None

    def test_partial_response_flags_missing(self):
        raw = json.dumps({"system_a": {"g": 7}, "system_b": {}, "notes": ""})
        a, b, notes, error = parse_judge_response(raw, ["g", "s"])
        assert a == {"g": 7, "s": None}
        assert b == {"g": None, "s": None}
        assert error is not None
        assert "system_a" in error and "s" in error
        assert "system_b" in error


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _judgment(qid: str, tier: str, rag: dict[str, int], wiki: dict[str, int]) -> JudgmentResult:
    return JudgmentResult(
        question_id=qid,
        tier=tier,
        bias="neutral",
        judge_model="test-judge",
        blinding={"A": SYSTEM_RAG, "B": SYSTEM_WIKI},
        rag_scores={k: v for k, v in rag.items()},
        wiki_scores={k: v for k, v in wiki.items()},
        notes="",
        raw_response="",
    )


class TestAggregate:
    def test_overall_means(self):
        criteria = ["g", "s"]
        judgments = [
            _judgment("q1", "multi-hop", {"g": 8, "s": 6}, {"g": 9, "s": 8}),
            _judgment("q2", "multi-hop", {"g": 7, "s": 5}, {"g": 9, "s": 9}),
            _judgment("q3", "bias-check", {"g": 9, "s": 7}, {"g": 6, "s": 4}),
        ]
        agg = aggregate(judgments, criteria)
        # RAG g mean = (8+7+9)/3 = 8.0; Wiki g mean = (9+9+6)/3 = 8.0
        assert agg["overall"]["rag"]["g"] == 8.0
        assert agg["overall"]["wiki"]["g"] == 8.0

    def test_by_tier_breakdown(self):
        criteria = ["g"]
        judgments = [
            _judgment("q1", "multi-hop", {"g": 8}, {"g": 9}),
            _judgment("q2", "multi-hop", {"g": 6}, {"g": 9}),
            _judgment("q3", "bias-check", {"g": 9}, {"g": 6}),
        ]
        agg = aggregate(judgments, criteria)
        assert agg["by_tier"]["multi-hop"]["rag"]["g"] == 7.0
        assert agg["by_tier"]["multi-hop"]["wiki"]["g"] == 9.0
        assert agg["by_tier"]["bias-check"]["rag"]["g"] == 9.0
        assert agg["by_tier"]["bias-check"]["wiki"]["g"] == 6.0
        assert agg["by_tier"]["multi-hop"]["n"] == 2
        assert agg["by_tier"]["bias-check"]["n"] == 1

    def test_skips_none_scores(self):
        criteria = ["g"]
        judgments = [
            _judgment("q1", "t", {"g": 8}, {"g": 9}),
            _judgment("q2", "t", {"g": None}, {"g": 7}),  # type: ignore[dict-item]
        ]
        agg = aggregate(judgments, criteria)
        # RAG mean uses only the one valid score.
        assert agg["overall"]["rag"]["g"] == 8.0
        assert agg["overall"]["wiki"]["g"] == 8.0


class TestInterRaterDeltas:
    def test_max_deltas_per_criterion(self):
        primary = [_judgment("q1", "t", {"g": 9}, {"g": 5})]
        secondary = [_judgment("q1", "t", {"g": 6}, {"g": 8})]
        out = _inter_rater_deltas(primary, secondary, ["g"])
        # rag delta = |9-6|=3, wiki delta = |5-8|=3 — max for g is 3.
        assert out["max_deltas"]["g"] == 3
        assert out["per_question"][0]["question_id"] == "q1"


# ---------------------------------------------------------------------------
# Dry-run / CLI
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_call_litellm(self, runs, rubric_path, tmp_path, capsys):
        rag, wiki = runs
        results_dir = tmp_path / "out"
        with patch("scripts.judge_runs.judge_one") as mocked:
            rc = main([
                "--rag-run", str(rag),
                "--wiki-run", str(wiki),
                "--rubric", str(rubric_path),
                "--results-dir", str(results_dir),
                "--dry-run",
            ])
        assert rc == 0
        mocked.assert_not_called()
        out = capsys.readouterr().out
        assert "Dry run" in out
        assert "q1" in out
        assert "q2" in out

    def test_dry_run_blinding_with_seed_is_stable(self, runs, rubric_path, tmp_path, capsys):
        rag, wiki = runs
        for seed in (0, 7, 42):
            with patch("scripts.judge_runs.judge_one"):
                main([
                    "--rag-run", str(rag),
                    "--wiki-run", str(wiki),
                    "--rubric", str(rubric_path),
                    "--results-dir", str(tmp_path / "out"),
                    "--seed", str(seed),
                    "--dry-run",
                ])
            first = capsys.readouterr().out
            with patch("scripts.judge_runs.judge_one"):
                main([
                    "--rag-run", str(rag),
                    "--wiki-run", str(wiki),
                    "--rubric", str(rubric_path),
                    "--results-dir", str(tmp_path / "out"),
                    "--seed", str(seed),
                    "--dry-run",
                ])
            second = capsys.readouterr().out
            assert first == second
