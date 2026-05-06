"""Unit tests for the batch-ingest CLI."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from scripts.ingest_corpus import (
    IngestRecord,
    _build_payload,
    already_ingested_filename,
    build_parser,
    main,
    planned_documents,
    poll_until_terminal,
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
    def test_finds_pipeline_complete_status(self):
        """Pipeline emits status='complete' for successful ingest."""
        existing = [
            {"id": "1", "filename": "a.pdf", "status": "complete"},
            {"id": "2", "filename": "b.pdf", "status": "failed"},
        ]
        hit = already_ingested_filename(existing, "a.pdf")
        assert hit and hit["id"] == "1"

    def test_finds_wiki_completed_status(self):
        """Also accepts 'completed' for compatibility with the wiki-side schema."""
        existing = [
            {"id": "1", "filename": "a.pdf", "status": "completed"},
        ]
        hit = already_ingested_filename(existing, "a.pdf")
        assert hit and hit["id"] == "1"

    def test_skips_non_terminal_match(self):
        existing = [
            {"id": "1", "filename": "a.pdf", "status": "parsing"},
        ]
        assert already_ingested_filename(existing, "a.pdf") is None

    def test_skips_failed_match(self):
        existing = [
            {"id": "1", "filename": "a.pdf", "status": "failed"},
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

        def fake_post(url, files=None, data=None, params=None):
            captured["url"] = url
            captured["files_keys"] = list((files or {}).keys())
            captured["data"] = data
            captured["params"] = params
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
        # collection_id rides as a query param to match the route's signature
        # (FastAPI treats unannotated str params as query, not form).
        assert captured["params"] == {"collection_id": "col-1"}
        # tags_json stays as form data (route declares it as Form(None)).
        import json as _json
        assert _json.loads(captured["data"]["tags_json"]) == {
            "role": "Anchor",
            "year": 2026,
        }
        assert "collection_id" not in captured["data"]


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


def _record(domain: str, role: str, secs: float, p: int | None, c: int | None) -> IngestRecord:
    return IngestRecord(
        filename=f"{domain}-{role}.pdf",
        domain=domain,
        role=role,
        document_id="x",
        status="complete",
        ingestion_seconds=secs,
        chunk_count=10,
        error_message=None,
        file_size_bytes=1234,
        prompt_tokens=p,
        completion_tokens=c,
    )


class TestPollUntilTerminal:
    """A 404 immediately after upload must be tolerated, not surfaced as failure.

    FastAPI commits the upload's DB session AFTER sending the 201, so a
    sub-second poll can race the commit and see no row yet.
    """

    def _make_response(self, status_code: int, payload: dict | None = None):
        resp = MagicMock()
        resp.status_code = status_code

        def _raise_for_status():
            if status_code >= 400:
                from httpx import HTTPStatusError, Request, Response

                req = Request("GET", "http://x/")
                raise HTTPStatusError("err", request=req, response=Response(status_code))

        resp.raise_for_status.side_effect = _raise_for_status
        resp.json.return_value = payload or {}
        return resp

    def test_initial_404_then_complete_succeeds(self):
        from scripts import ingest_corpus as mod

        client = MagicMock()
        client.get.side_effect = [
            self._make_response(404),
            self._make_response(200, {"status": "complete", "id": "x"}),
        ]
        with patch.object(mod.time, "sleep"):
            doc = poll_until_terminal(client, "x", interval=0.1, timeout=10.0)
        assert doc["status"] == "complete"
        assert client.get.call_count == 2

    def test_persistent_404_past_grace_window_raises(self):
        from scripts import ingest_corpus as mod

        client = MagicMock()
        client.get.return_value = self._make_response(404)

        # Fake monotonic clock so we cross the 30s grace window after one tick.
        ticks = iter([0.0, 0.0, 100.0])  # start, deadline calc, second poll
        with patch.object(mod.time, "monotonic", side_effect=lambda: next(ticks)):
            with patch.object(mod.time, "sleep"):
                import pytest as _pytest
                from httpx import HTTPStatusError

                with _pytest.raises(HTTPStatusError):
                    poll_until_terminal(client, "x", interval=0.1, timeout=10.0)

    def test_non_terminal_status_continues_polling(self):
        from scripts import ingest_corpus as mod

        client = MagicMock()
        client.get.side_effect = [
            self._make_response(200, {"status": "parsing"}),
            self._make_response(200, {"status": "embedding"}),
            self._make_response(200, {"status": "complete"}),
        ]
        with patch.object(mod.time, "sleep"):
            doc = poll_until_terminal(client, "x", interval=0.1, timeout=10.0)
        assert doc["status"] == "complete"
        assert client.get.call_count == 3

    def test_failed_is_terminal(self):
        from scripts import ingest_corpus as mod

        client = MagicMock()
        client.get.side_effect = [
            self._make_response(200, {"status": "parsing"}),
            self._make_response(200, {"status": "failed", "error_message": "boom"}),
        ]
        with patch.object(mod.time, "sleep"):
            doc = poll_until_terminal(client, "x", interval=0.1, timeout=10.0)
        assert doc["status"] == "failed"


class TestPayloadAggregation:
    """Per-domain rollup includes the new prompt/completion token totals."""

    def _corpus_stub(self, tmp_path: Path):
        manifest = tmp_path / "corpus.yaml"
        manifest.write_text(yaml.safe_dump({"ingest_order": [], "collections": []}))
        return load_corpus(manifest)

    def test_by_domain_sums_tokens_and_seconds(self, tmp_path: Path):
        corpus = self._corpus_stub(tmp_path)
        records = [
            _record("ai-ethics-law", "Anchor", 12.0, 1000, 200),
            _record("ai-ethics-law", "Conflict", 8.0, 500, 100),
            _record("climate-science", "Anchor", 15.0, 2000, 400),
        ]
        args = argparse.Namespace(base_url="http://localhost:8000")

        payload = _build_payload(corpus, records, "20260506T120000Z", args)

        ai = payload["totals"]["by_domain"]["ai-ethics-law"]
        assert ai["documents"] == 2
        assert ai["completed"] == 2
        assert ai["total_seconds"] == 20.0
        assert ai["prompt_tokens"] == 1500
        assert ai["completion_tokens"] == 300

        cs = payload["totals"]["by_domain"]["climate-science"]
        assert cs["prompt_tokens"] == 2000
        assert cs["completion_tokens"] == 400

        assert payload["totals"]["prompt_tokens"] == 3500
        assert payload["totals"]["completion_tokens"] == 700

    def test_missing_token_counts_treated_as_zero(self, tmp_path: Path):
        corpus = self._corpus_stub(tmp_path)
        records = [
            _record("d", "Anchor", 5.0, None, None),
            _record("d", "Bridge", 7.0, 100, 20),
        ]
        args = argparse.Namespace(base_url="http://localhost:8000")

        payload = _build_payload(corpus, records, "ts", args)

        d = payload["totals"]["by_domain"]["d"]
        assert d["prompt_tokens"] == 100
        assert d["completion_tokens"] == 20
        assert payload["totals"]["prompt_tokens"] == 100
