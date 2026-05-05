"""Unit tests for the batch-ingest CLI."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from scripts.ingest_corpus import (
    already_ingested_filename,
    build_parser,
    main,
    planned_documents,
    upload_document,
)
from scripts._common import load_corpus


def _write_manifest(tmp_path: Path) -> Path:
    """Create a 1-collection manifest with 4 docs and matching dummy PDFs."""
    papers = tmp_path / "papers" / "test-domain"
    papers.mkdir(parents=True)
    for name in ("a_anchor.pdf", "b_conflict.pdf", "c_chrono.pdf", "d_bridge.pdf"):
        (papers / name).write_bytes(b"%PDF-1.4 dummy")

    data = {
        "ingest_order": ["Anchor", "Chrono", "Bridge", "Conflict"],
        "collections": [
            {
                "name": "test-domain",
                "description": "x",
                "documents": [
                    {"file": "papers/test-domain/a_anchor.pdf",
                     "tags": {"domain": "test-domain", "role": "Anchor"}},
                    {"file": "papers/test-domain/b_conflict.pdf",
                     "tags": {"domain": "test-domain", "role": "Conflict"}},
                    {"file": "papers/test-domain/c_chrono.pdf",
                     "tags": {"domain": "test-domain", "role": "Chrono"}},
                    {"file": "papers/test-domain/d_bridge.pdf",
                     "tags": {"domain": "test-domain", "role": "Bridge"}},
                ],
            }
        ],
    }
    p = tmp_path / "corpus.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


class TestPlannedDocuments:
    def test_documents_are_ordered_by_role(self, tmp_path: Path):
        manifest = _write_manifest(tmp_path)
        corpus = load_corpus(manifest)
        plan = planned_documents(corpus, only=None)

        order = [doc.tags["role"] for _, doc in plan]
        assert order == ["Anchor", "Chrono", "Bridge", "Conflict"]

    def test_only_filter_substring(self, tmp_path: Path):
        manifest = _write_manifest(tmp_path)
        corpus = load_corpus(manifest)
        plan = planned_documents(corpus, only="anchor")
        assert len(plan) == 1
        assert plan[0][1].file.name == "a_anchor.pdf"


class TestAlreadyIngested:
    def test_finds_completed_match(self):
        existing = [
            {"id": "1", "filename": "a.pdf", "status": "completed"},
            {"id": "2", "filename": "b.pdf", "status": "error"},
        ]
        hit = already_ingested_filename(existing, "a.pdf")
        assert hit and hit["id"] == "1"

    def test_skips_non_completed_match(self):
        existing = [
            {"id": "1", "filename": "a.pdf", "status": "processing"},
        ]
        assert already_ingested_filename(existing, "a.pdf") is None

    def test_returns_none_when_filename_unknown(self):
        assert already_ingested_filename([], "anything.pdf") is None


class TestUploadDocumentPayload:
    def test_includes_tags_json_in_form_data(self, tmp_path: Path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4 dummy")

        captured = {}

        class _FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return [{"id": "abc-123"}]

        def fake_post(url, files=None, data=None):
            captured["url"] = url
            captured["files_keys"] = list((files or {}).keys())
            captured["data"] = data
            return _FakeResponse()

        client = MagicMock()
        client.post.side_effect = fake_post

        doc_id = upload_document(
            client,
            collection_id="col-1",
            pdf=pdf,
            tags={"role": "Anchor", "year": 2026},
        )

        assert doc_id == "abc-123"
        assert captured["url"] == "/api/documents/upload"
        assert captured["files_keys"] == ["files"]
        assert captured["data"]["collection_id"] == "col-1"
        # tags get JSON-encoded into the form value
        import json as _json
        assert _json.loads(captured["data"]["tags_json"]) == {
            "role": "Anchor",
            "year": 2026,
        }


class TestDryRun:
    def test_dry_run_does_not_call_backend(self, tmp_path: Path, capsys):
        manifest = _write_manifest(tmp_path)
        results_dir = tmp_path / "results"

        with patch("scripts.ingest_corpus.make_client") as mc:
            rc = main([
                "--manifest", str(manifest),
                "--results-dir", str(results_dir),
                "--dry-run",
            ])

        assert rc == 0
        mc.assert_not_called()
        captured = capsys.readouterr()
        assert "Dry run" in captured.out
        assert "a_anchor.pdf" in captured.out


class TestParser:
    def test_argparse_defaults(self):
        parser = build_parser()
        ns = parser.parse_args([])
        assert ns.base_url == "http://localhost:8000"
        assert ns.poll_interval == 2.0
        assert ns.dry_run is False
