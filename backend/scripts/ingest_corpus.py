"""Batch-ingest the experiment corpus into the running rag2compare backend.

Reads experiments/corpus.yaml, creates each named collection if it doesn't
already exist, then uploads every PDF in the manifest in role order
(Anchor -> Chrono -> Bridge -> Conflict by default). Polls each document
to completion and writes a per-paper timing report to
experiments/results/ingest-<timestamp>.json — the artifact you compare
against the LLM Wiki side's per-paper ingest log.

Usage:
    python -m scripts.ingest_corpus [--base-url http://localhost:8000] \\
        [--manifest experiments/corpus.yaml] [--only filename.pdf] \\
        [--dry-run] [--skip-completed] [--poll-interval 2.0] \\
        [--poll-timeout 1800]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from scripts._common import (
    Corpus,
    CorpusCollection,
    CorpusDocument,
    err,
    info,
    load_corpus,
    make_client,
    role_sort_key,
    utc_timestamp,
    write_json,
)

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_MANIFEST = "experiments/corpus.yaml"
DEFAULT_RESULTS_DIR = "experiments/results"

TERMINAL_STATUSES = {"complete", "failed"}
SUCCESS_STATUSES = {"complete", "completed"}


@dataclass
class IngestRecord:
    filename: str
    domain: str
    role: str
    document_id: str | None
    status: str
    ingestion_seconds: float | None
    chunk_count: int | None
    error_message: str | None
    file_size_bytes: int | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def ensure_collection(
    client: httpx.Client, name: str, description: str
) -> str:
    """Return the id of the collection, creating it if missing."""
    resp = client.get("/api/collections")
    resp.raise_for_status()
    for col in resp.json():
        if col["name"] == name:
            return col["id"]

    create = client.post(
        "/api/collections",
        json={"name": name, "description": description or None},
    )
    create.raise_for_status()
    return create.json()["id"]


def collection_documents(client: httpx.Client, collection_id: str) -> list[dict]:
    resp = client.get("/api/documents", params={"collection_id": collection_id})
    resp.raise_for_status()
    return resp.json()


def upload_document(
    client: httpx.Client,
    collection_id: str,
    pdf: Path,
    tags: dict,
) -> str:
    """POST /documents/upload with one PDF + tags_json. Returns the new doc id.

    The backend reads `collection_id` as a query parameter (it's not
    annotated with `Form()` in the route), so we pass it via params.
    `tags_json` stays as a form field to match the route's `Form()` declaration.
    """
    with pdf.open("rb") as fh:
        files = {"files": (pdf.name, fh, "application/pdf")}
        data = {"tags_json": json.dumps(tags)}
        resp = client.post(
            "/api/documents/upload",
            files=files,
            data=data,
            params={"collection_id": collection_id},
        )
    resp.raise_for_status()
    body = resp.json()
    if not body:
        raise RuntimeError(f"upload returned no documents for {pdf}")
    return body[0]["id"]


_NOT_FOUND_GRACE_SECONDS = 30.0


def poll_until_terminal(
    client: httpx.Client,
    document_id: str,
    interval: float,
    timeout: float,
) -> dict:
    """Poll GET /documents/{id} until status is terminal or timeout fires.

    A 404 immediately after upload is expected: FastAPI returns the 201
    response before its dependency-injected DB session commits, so a fresh
    GET can briefly miss the row. We tolerate 404s for `_NOT_FOUND_GRACE_SECONDS`
    after the first poll, then surface them as real failures.
    """
    deadline = time.monotonic() + timeout
    not_found_deadline = time.monotonic() + _NOT_FOUND_GRACE_SECONDS
    while True:
        resp = client.get(f"/api/documents/{document_id}")
        if resp.status_code == 404 and time.monotonic() < not_found_deadline:
            time.sleep(interval)
            continue
        resp.raise_for_status()
        doc = resp.json()
        if doc["status"] in TERMINAL_STATUSES:
            return doc
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"document {document_id} did not reach a terminal status within {timeout}s"
                f" (last status: {doc['status']})"
            )
        time.sleep(interval)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def planned_documents(
    corpus: Corpus, only: str | None
) -> list[tuple[CorpusCollection, CorpusDocument]]:
    """Flatten the manifest into a (collection, doc) list in role order."""
    plan: list[tuple[CorpusCollection, CorpusDocument]] = []
    for collection in corpus.collections:
        sorted_docs = sorted(
            collection.documents,
            key=lambda d: role_sort_key(corpus.ingest_order, d.role),
        )
        for doc in sorted_docs:
            if only and only not in doc.file.name:
                continue
            plan.append((collection, doc))
    return plan


def already_ingested_filename(existing: list[dict], pdf_name: str) -> dict | None:
    """Find an existing Document row matching a PDF filename, if any."""
    for d in existing:
        if d["filename"] == pdf_name and d["status"] in SUCCESS_STATUSES:
            return d
    return None


def run(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        err(f"manifest not found: {manifest_path}")
        return 2

    corpus = load_corpus(manifest_path)
    plan = planned_documents(corpus, args.only)
    if not plan:
        err("no documents matched the filter; nothing to do")
        return 1

    # Pre-flight: every planned PDF must exist on disk.
    missing = [(c.name, d.file) for c, d in plan if not d.file.exists()]
    if missing:
        err(
            f"{len(missing)} PDF(s) referenced in the manifest are missing on disk:\n"
            + "\n".join(f"  - [{name}] {p}" for name, p in missing)
        )
        if not args.dry_run:
            return 2

    info(
        f"manifest: {manifest_path}\n"
        f"backend:  {args.base_url}\n"
        f"plan:     {len(plan)} document(s) across {len(corpus.collections)} collection(s)"
    )

    if args.dry_run:
        info("\nDry run — would ingest in this order:")
        for collection, doc in plan:
            mark = " " if doc.file.exists() else "?"
            info(f"  [{mark}] {collection.name:20s} {doc.role:20s} {doc.file.name}")
        return 0

    started = utc_timestamp()
    records: list[IngestRecord] = []

    with make_client(args.base_url) as client:
        # Health probe — fail fast if the backend isn't up.
        try:
            health = client.get("/api/health")
            health.raise_for_status()
        except Exception as e:  # noqa: BLE001
            err(f"backend health check failed: {e}")
            return 2

        # Collection name -> id
        col_ids: dict[str, str] = {}
        for collection in corpus.collections:
            col_ids[collection.name] = ensure_collection(
                client, collection.name, collection.description
            )
            info(f"collection {collection.name} -> {col_ids[collection.name]}")

        # Cache existing docs per collection so --skip-completed is cheap.
        existing_by_col = (
            {cid: collection_documents(client, cid) for cid in col_ids.values()}
            if args.skip_completed
            else {}
        )

        for collection, doc in plan:
            cid = col_ids[collection.name]
            if args.skip_completed:
                hit = already_ingested_filename(
                    existing_by_col.get(cid, []), doc.file.name
                )
                if hit:
                    info(
                        f"skip   [{collection.name}] {doc.role:20s} {doc.file.name} "
                        f"(already completed in {hit.get('ingestion_seconds')}s)"
                    )
                    records.append(
                        IngestRecord(
                            filename=doc.file.name,
                            domain=doc.domain,
                            role=doc.role,
                            document_id=hit["id"],
                            status=hit.get("status") or "complete",
                            ingestion_seconds=hit.get("ingestion_seconds"),
                            chunk_count=hit.get("chunk_count"),
                            error_message=None,
                            file_size_bytes=hit.get("file_size_bytes"),
                            prompt_tokens=hit.get("ingestion_prompt_tokens"),
                            completion_tokens=hit.get("ingestion_completion_tokens"),
                        )
                    )
                    continue

            info(f"upload [{collection.name}] {doc.role:20s} {doc.file.name}")
            try:
                document_id = upload_document(client, cid, doc.file, doc.tags)
            except Exception as e:  # noqa: BLE001
                err(f"upload failed for {doc.file.name}: {e}")
                records.append(
                    IngestRecord(
                        filename=doc.file.name,
                        domain=doc.domain,
                        role=doc.role,
                        document_id=None,
                        status="upload_failed",
                        ingestion_seconds=None,
                        chunk_count=None,
                        error_message=str(e),
                        file_size_bytes=doc.file.stat().st_size if doc.file.exists() else None,
                    )
                )
                continue

            try:
                final = poll_until_terminal(
                    client, document_id, args.poll_interval, args.poll_timeout
                )
            except TimeoutError as e:
                err(str(e))
                records.append(
                    IngestRecord(
                        filename=doc.file.name,
                        domain=doc.domain,
                        role=doc.role,
                        document_id=document_id,
                        status="timeout",
                        ingestion_seconds=None,
                        chunk_count=None,
                        error_message=str(e),
                        file_size_bytes=doc.file.stat().st_size if doc.file.exists() else None,
                    )
                )
                continue

            secs = final.get("ingestion_seconds")
            info(
                f"  -> {final['status']:>9s}  {secs:.2f}s" if secs is not None
                else f"  -> {final['status']:>9s}  (no timing)"
            )
            records.append(
                IngestRecord(
                    filename=doc.file.name,
                    domain=doc.domain,
                    role=doc.role,
                    document_id=document_id,
                    status=final["status"],
                    ingestion_seconds=secs,
                    chunk_count=final.get("chunk_count"),
                    error_message=final.get("error_message"),
                    file_size_bytes=final.get("file_size_bytes"),
                    prompt_tokens=final.get("ingestion_prompt_tokens"),
                    completion_tokens=final.get("ingestion_completion_tokens"),
                )
            )

    payload = _build_payload(corpus, records, started, args)
    out = Path(args.results_dir) / f"ingest-{started}.json"
    write_json(out, payload)
    info(f"\nwrote ingest report -> {out}")
    return 0


def _build_payload(
    corpus: Corpus,
    records: list[IngestRecord],
    started: str,
    args: argparse.Namespace,
) -> dict:
    by_domain: dict[str, dict] = {}
    for r in records:
        d = by_domain.setdefault(
            r.domain,
            {
                "documents": 0,
                "completed": 0,
                "total_seconds": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            },
        )
        d["documents"] += 1
        if r.status in SUCCESS_STATUSES:
            d["completed"] += 1
        if r.ingestion_seconds:
            d["total_seconds"] += r.ingestion_seconds
        if r.prompt_tokens:
            d["prompt_tokens"] += r.prompt_tokens
        if r.completion_tokens:
            d["completion_tokens"] += r.completion_tokens

    total_seconds = sum((r.ingestion_seconds or 0.0) for r in records)
    total_prompt_tokens = sum((r.prompt_tokens or 0) for r in records)
    total_completion_tokens = sum((r.completion_tokens or 0) for r in records)
    completed = sum(1 for r in records if r.status in SUCCESS_STATUSES)

    return {
        "started_at": started,
        "manifest": str(corpus.manifest_path),
        "backend_url": args.base_url,
        "documents": [r.__dict__ for r in records],
        "totals": {
            "documents": len(records),
            "completed": completed,
            "total_seconds": round(total_seconds, 3),
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "by_domain": {
                k: {**v, "total_seconds": round(v["total_seconds"], 3)}
                for k, v in by_domain.items()
            },
        },
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"rag2compare backend base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--manifest", default=DEFAULT_MANIFEST,
                   help=f"corpus manifest path (default: {DEFAULT_MANIFEST})")
    p.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR,
                   help=f"where to write ingest-<ts>.json (default: {DEFAULT_RESULTS_DIR})")
    p.add_argument("--only", default=None,
                   help="if set, only ingest documents whose filename contains this substring")
    p.add_argument("--skip-completed", action="store_true",
                   help="skip documents already marked completed in the target collection")
    p.add_argument("--poll-interval", type=float, default=2.0,
                   help="seconds between status polls (default: 2.0)")
    p.add_argument("--poll-timeout", type=float, default=1800.0,
                   help="per-document max polling time in seconds (default: 1800)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the planned ingestion order without uploading")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
