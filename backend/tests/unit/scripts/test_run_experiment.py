"""Unit tests for the experiment-runner CLI."""

from pathlib import Path
from unittest.mock import patch

import yaml

from scripts._common import EvalQuestion
from scripts.run_experiment import (
    build_parser,
    build_query_payload,
    filter_collections,
    filter_questions,
    main,
    resolve_collections,
)


def _write_questions(tmp_path: Path) -> Path:
    data = {
        "questions": [
            {"id": "q1", "tier": "multi-hop", "bias": "wiki",
             "collections": ["a", "b"], "text": "synthesize"},
            {"id": "q2", "tier": "bias-check", "bias": "rag",
             "collections": ["a"], "text": "exact stat?"},
            {"id": "q3", "tier": "policy", "bias": "wiki",
             "collections": ["a", "b", "c"], "text": "policy"},
        ]
    }
    p = tmp_path / "questions.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


class TestBuildQueryPayload:
    def test_payload_shape(self):
        q = EvalQuestion(
            id="q1", tier="multi-hop", bias="wiki",
            collections=["a"], text="hello",
        )
        body = build_query_payload(q, ["uuid-a"], "xhigh")
        assert body == {
            "query": "hello",
            "collection_ids": ["uuid-a"],
            "options": {"reasoning_effort": "xhigh"},
        }

    def test_off_reasoning_effort_passes_through(self):
        q = EvalQuestion(
            id="q1", tier="bias-check", bias="rag",
            collections=["a"], text="stat?",
        )
        body = build_query_payload(q, ["uuid-a"], "off")
        assert body["options"]["reasoning_effort"] == "off"


class TestResolveCollections:
    def test_resolves_present_names(self):
        ids, missing = resolve_collections(
            {"a": "uuid-a", "b": "uuid-b"}, ["a", "b"]
        )
        assert ids == ["uuid-a", "uuid-b"]
        assert missing == []

    def test_reports_missing(self):
        ids, missing = resolve_collections({"a": "uuid-a"}, ["a", "z"])
        assert ids == ["uuid-a"]
        assert missing == ["z"]


class TestFilterCollections:
    def test_no_allowed_means_passthrough(self):
        assert filter_collections(["a", "b"], None) == ["a", "b"]

    def test_subset_filter(self):
        assert filter_collections(["a", "b", "c"], {"a", "c"}) == ["a", "c"]

    def test_empty_filter_means_skip(self):
        # If --collections excludes all of a question's targets, the runner
        # later treats the empty list as "skip this question".
        assert filter_collections(["a", "b"], {"x"}) == []


class TestFilterQuestions:
    def test_only_tier(self):
        qs = [
            EvalQuestion(id="q1", tier="multi-hop", bias="wiki",
                         collections=["a"], text="x"),
            EvalQuestion(id="q2", tier="policy", bias="wiki",
                         collections=["a"], text="y"),
        ]
        assert [q.id for q in filter_questions(qs, "multi-hop", None)] == ["q1"]

    def test_only_id(self):
        qs = [
            EvalQuestion(id="q1", tier="multi-hop", bias="wiki",
                         collections=["a"], text="x"),
            EvalQuestion(id="q2", tier="policy", bias="wiki",
                         collections=["a"], text="y"),
        ]
        assert [q.id for q in filter_questions(qs, None, "q2")] == ["q2"]


class TestDryRun:
    def test_dry_run_does_not_call_backend(self, tmp_path: Path, capsys):
        questions = _write_questions(tmp_path)
        results_dir = tmp_path / "results"

        with patch("scripts.run_experiment.make_client") as mc:
            rc = main([
                "--questions", str(questions),
                "--results-dir", str(results_dir),
                "--dry-run",
            ])

        assert rc == 0
        mc.assert_not_called()
        captured = capsys.readouterr()
        assert "Dry run" in captured.out
        assert "q1" in captured.out
        assert "q2" in captured.out

    def test_dry_run_respects_only_tier(self, tmp_path: Path, capsys):
        questions = _write_questions(tmp_path)
        results_dir = tmp_path / "results"

        rc = main([
            "--questions", str(questions),
            "--results-dir", str(results_dir),
            "--dry-run",
            "--only-tier", "policy",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "q3" in out
        assert "q1" not in out


class TestParser:
    def test_argparse_defaults(self):
        ns = build_parser().parse_args([])
        assert ns.base_url == "http://localhost:8000"
        assert ns.reasoning_effort == "xhigh"
        assert ns.repeat == 1
        assert ns.dry_run is False
