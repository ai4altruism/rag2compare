"""Unit tests for the shared CLI helpers — manifest parsing + role ordering."""

from pathlib import Path

import pytest
import yaml

from scripts._common import (
    Corpus,
    EvalQuestion,
    load_corpus,
    load_questions,
    role_sort_key,
)


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    data = {
        "ingest_order": ["Anchor", "Chrono", "Bridge", "Conflict"],
        "collections": [
            {
                "name": "test-domain",
                "description": "x",
                "documents": [
                    {
                        "file": "papers/test-domain/a_anchor.pdf",
                        "tags": {"domain": "test-domain", "role": "Anchor", "year": 2024},
                    },
                    {
                        "file": "papers/test-domain/b_conflict.pdf",
                        "tags": {"domain": "test-domain", "role": "Conflict"},
                    },
                    {
                        "file": "papers/test-domain/c_chrono_anchor.pdf",
                        "tags": {"domain": "test-domain", "role": "Chrono/Anchor"},
                    },
                    {
                        "file": "papers/test-domain/d_bridge.pdf",
                        "tags": {"domain": "test-domain", "role": "Bridge"},
                    },
                ],
            }
        ],
    }
    p = tmp_path / "corpus.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


class TestLoadCorpus:
    def test_resolves_paths_relative_to_manifest(self, manifest: Path):
        corpus = load_corpus(manifest)
        assert isinstance(corpus, Corpus)
        assert len(corpus.collections) == 1
        col = corpus.collections[0]
        assert col.name == "test-domain"
        assert len(col.documents) == 4
        for doc in col.documents:
            assert doc.file.is_absolute()
            assert doc.file.parent.name == "test-domain"

    def test_preserves_tags(self, manifest: Path):
        corpus = load_corpus(manifest)
        anchor = corpus.collections[0].documents[0]
        assert anchor.role == "Anchor"
        assert anchor.domain == "test-domain"
        assert anchor.tags["year"] == 2024


class TestRoleSortKey:
    def test_known_roles_sort_in_listed_order(self):
        order = ["Anchor", "Chrono", "Bridge", "Conflict"]
        keys = [role_sort_key(order, r)[0] for r in order]
        assert keys == [0, 1, 2, 3]

    def test_compound_role_uses_first_segment(self):
        order = ["Anchor", "Chrono", "Bridge", "Conflict"]
        # "Chrono/Anchor" should sort with Chrono (index 1), not Anchor.
        assert role_sort_key(order, "Chrono/Anchor")[0] == 1

    def test_unknown_roles_go_to_end(self):
        order = ["Anchor", "Chrono"]
        assert role_sort_key(order, "Mystery")[0] == len(order)

    def test_case_insensitive(self):
        order = ["Anchor", "Chrono"]
        assert role_sort_key(order, "anchor")[0] == 0
        assert role_sort_key(order, "ANCHOR")[0] == 0


class TestLoadQuestions:
    def test_parses_questions(self, tmp_path: Path):
        data = {
            "questions": [
                {
                    "id": "q1",
                    "tier": "multi-hop",
                    "bias": "wiki",
                    "collections": ["a", "b"],
                    "text": "hello\n\nworld",
                },
                {
                    "id": "q2",
                    "tier": "bias-check",
                    "bias": "rag",
                    "collections": ["a"],
                    "text": "specific stat?",
                },
            ]
        }
        p = tmp_path / "questions.yaml"
        p.write_text(yaml.safe_dump(data))

        qset = load_questions(p)
        assert len(qset.questions) == 2
        assert isinstance(qset.questions[0], EvalQuestion)
        assert qset.questions[0].id == "q1"
        assert qset.questions[0].collections == ["a", "b"]
        # The text gets stripped of trailing whitespace.
        assert qset.questions[0].text == "hello\n\nworld"

    def test_missing_questions_key_raises(self, tmp_path: Path):
        p = tmp_path / "bad.yaml"
        p.write_text("foo: bar\n")
        with pytest.raises(ValueError, match="missing 'questions:'"):
            load_questions(p)
