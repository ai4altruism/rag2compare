"""Shared helpers for the experiment CLIs.

Both ingest_corpus.py and run_experiment.py drive the running rag2compare
backend over its REST API. We deliberately do not import the FastAPI
pipeline modules here so that the CLIs are useful against a remote
instance, not just a local in-process one.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml


# ---------------------------------------------------------------------------
# Manifest schema  (keep in sync with experiments/corpus.yaml)
# ---------------------------------------------------------------------------


@dataclass
class CorpusDocument:
    file: Path
    tags: dict[str, Any]

    @property
    def role(self) -> str:
        return str(self.tags.get("role", ""))

    @property
    def domain(self) -> str:
        return str(self.tags.get("domain", ""))


@dataclass
class CorpusCollection:
    name: str
    description: str
    documents: list[CorpusDocument]


@dataclass
class Corpus:
    ingest_order: list[str]
    collections: list[CorpusCollection]
    manifest_path: Path

    def all_documents(self) -> list[tuple[CorpusCollection, CorpusDocument]]:
        return [(c, d) for c in self.collections for d in c.documents]


def load_corpus(manifest_path: Path) -> Corpus:
    """Parse experiments/corpus.yaml. Resolves doc paths relative to the manifest."""
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"corpus manifest must be a YAML mapping: {manifest_path}")

    ingest_order = list(raw.get("ingest_order") or [])
    collections_raw = raw.get("collections") or []
    base = manifest_path.parent

    collections: list[CorpusCollection] = []
    for col in collections_raw:
        docs_raw = col.get("documents") or []
        docs = [
            CorpusDocument(
                file=(base / d["file"]).resolve(),
                tags=dict(d.get("tags") or {}),
            )
            for d in docs_raw
        ]
        collections.append(
            CorpusCollection(
                name=col["name"],
                description=str(col.get("description") or "").strip(),
                documents=docs,
            )
        )

    return Corpus(
        ingest_order=ingest_order,
        collections=collections,
        manifest_path=manifest_path,
    )


def role_sort_key(order: list[str], role: str) -> tuple[int, str]:
    """Ordering key for ingestion: anything in `order` first (in given order),
    then everything else alphabetically. Hyphenated/slashed roles match by
    their first segment so 'Chrono/Anchor' lines up under 'Chrono'.
    """
    base = role.split("/", 1)[0].strip() if role else ""
    for i, r in enumerate(order):
        if base.lower() == r.lower():
            return (i, role)
    return (len(order), role)


# ---------------------------------------------------------------------------
# Question schema  (keep in sync with experiments/questions.yaml)
# ---------------------------------------------------------------------------


@dataclass
class EvalQuestion:
    id: str
    tier: str
    bias: str
    collections: list[str]
    text: str


@dataclass
class QuestionSet:
    questions: list[EvalQuestion]
    questions_path: Path


def load_questions(path: Path) -> QuestionSet:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "questions" not in raw:
        raise ValueError(f"questions file missing 'questions:' key: {path}")
    qs = [
        EvalQuestion(
            id=q["id"],
            tier=str(q.get("tier", "")),
            bias=str(q.get("bias", "")),
            collections=list(q.get("collections") or []),
            text=str(q["text"]).strip(),
        )
        for q in raw["questions"]
    ]
    return QuestionSet(questions=qs, questions_path=path)


# ---------------------------------------------------------------------------
# Result writers
# ---------------------------------------------------------------------------


def utc_timestamp() -> str:
    """Compact UTC timestamp used in result filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(out_path: Path, payload: dict) -> Path:
    """Write a JSON payload (atomic-ish: write+rename)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(out_path)
    return out_path


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def make_client(base_url: str, timeout: float = 60.0) -> httpx.Client:
    """Synchronous httpx client. The CLIs are linear and benefit from simple
    blocking semantics; the backend itself is the async one."""
    return httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)


def err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(msg, flush=True)
