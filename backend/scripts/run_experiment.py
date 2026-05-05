"""Run the eval question set against the rag2compare backend.

For each question in experiments/questions.yaml, this CLI submits a
fresh /api/query request (no conversation context — see "Cold Start"
bias-check in the experimental design), captures the answer, sources,
and per-call telemetry, then writes everything to
experiments/results/run-<timestamp>.json.

Usage:
    python -m scripts.run_experiment [--base-url http://localhost:8000] \\
        [--questions experiments/questions.yaml] \\
        [--reasoning-effort xhigh] [--collections ai-ethics-law,...] \\
        [--repeat 1] [--only-tier multi-hop] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from scripts._common import (
    EvalQuestion,
    err,
    info,
    load_questions,
    make_client,
    utc_timestamp,
    write_json,
)

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_QUESTIONS = "experiments/questions.yaml"
DEFAULT_RESULTS_DIR = "experiments/results"


@dataclass
class QuestionResult:
    id: str
    repetition: int
    tier: str
    bias: str
    requested_collections: list[str]
    resolved_collection_ids: list[str]
    reasoning_effort: str
    text: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: str | None = None


# ---------------------------------------------------------------------------
# Collection name -> id resolver
# ---------------------------------------------------------------------------


def fetch_collection_ids(client: httpx.Client) -> dict[str, str]:
    resp = client.get("/api/collections")
    resp.raise_for_status()
    return {c["name"]: c["id"] for c in resp.json()}


def resolve_collections(
    name_to_id: dict[str, str], requested: list[str]
) -> tuple[list[str], list[str]]:
    """Return (resolved_ids, missing_names)."""
    missing = [n for n in requested if n not in name_to_id]
    resolved = [name_to_id[n] for n in requested if n in name_to_id]
    return resolved, missing


# ---------------------------------------------------------------------------
# Query submission
# ---------------------------------------------------------------------------


def build_query_payload(
    question: EvalQuestion,
    collection_ids: list[str],
    reasoning_effort: str,
) -> dict:
    """Construct the QueryRequest body for /api/query."""
    return {
        "query": question.text,
        "collection_ids": collection_ids,
        "options": {
            "reasoning_effort": reasoning_effort,
        },
    }


def submit_one(
    client: httpx.Client,
    payload: dict,
) -> tuple[dict, str | None]:
    """POST /api/query, return (parsed_response, error_message_or_none)."""
    try:
        resp = client.post("/api/query", json=payload)
        resp.raise_for_status()
        return resp.json(), None
    except httpx.HTTPStatusError as e:
        body: Any
        try:
            body = e.response.json()
        except Exception:  # noqa: BLE001
            body = e.response.text
        return {}, f"HTTP {e.response.status_code}: {body}"
    except Exception as e:  # noqa: BLE001
        return {}, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def filter_questions(
    questions: list[EvalQuestion],
    only_tier: str | None,
    only_id: str | None,
) -> list[EvalQuestion]:
    out = list(questions)
    if only_tier:
        out = [q for q in out if q.tier == only_tier]
    if only_id:
        out = [q for q in out if q.id == only_id]
    return out


def filter_collections(
    requested: list[str], allowed: set[str] | None
) -> list[str]:
    """Restrict a question's requested collections to those in --collections."""
    if allowed is None:
        return list(requested)
    return [c for c in requested if c in allowed]


def run(args: argparse.Namespace) -> int:
    questions_path = Path(args.questions).resolve()
    if not questions_path.exists():
        err(f"questions file not found: {questions_path}")
        return 2

    qset = load_questions(questions_path)
    questions = filter_questions(qset.questions, args.only_tier, args.only_id)
    if not questions:
        err("no questions matched the filter; nothing to do")
        return 1

    allowed_collections: set[str] | None = None
    if args.collections:
        allowed_collections = {
            c.strip() for c in args.collections.split(",") if c.strip()
        }

    info(
        f"questions: {questions_path}\n"
        f"backend:   {args.base_url}\n"
        f"effort:    {args.reasoning_effort}\n"
        f"plan:      {len(questions)} question(s) x {args.repeat} repetition(s)"
    )

    if args.dry_run:
        info("\nDry run — would submit the following:")
        for q in questions:
            cols = filter_collections(q.collections, allowed_collections)
            info(
                f"  [{q.tier:14s} | {q.bias:7s}] {q.id}  "
                f"collections={cols}"
            )
        return 0

    started = utc_timestamp()
    results: list[QuestionResult] = []

    with make_client(args.base_url, timeout=600.0) as client:
        try:
            health = client.get("/api/health")
            health.raise_for_status()
        except Exception as e:  # noqa: BLE001
            err(f"backend health check failed: {e}")
            return 2

        name_to_id = fetch_collection_ids(client)

        for rep in range(1, args.repeat + 1):
            for q in questions:
                requested = filter_collections(q.collections, allowed_collections)
                if not requested:
                    info(f"skip [{q.id}] no requested collections after filter")
                    continue

                resolved, missing = resolve_collections(name_to_id, requested)
                if missing:
                    info(
                        f"skip [{q.id}] missing collections in backend: {missing} "
                        f"(have: {sorted(name_to_id)})"
                    )
                    continue

                effort = args.reasoning_effort
                payload = build_query_payload(q, resolved, effort)

                info(
                    f"ask  [{q.id}] tier={q.tier} bias={q.bias} "
                    f"rep={rep}/{args.repeat} collections={requested}"
                )
                response, error = submit_one(client, payload)

                if error:
                    err(f"  -> failed: {error}")
                    results.append(
                        QuestionResult(
                            id=q.id,
                            repetition=rep,
                            tier=q.tier,
                            bias=q.bias,
                            requested_collections=requested,
                            resolved_collection_ids=resolved,
                            reasoning_effort=effort,
                            text=q.text,
                            answer="",
                            error=error,
                        )
                    )
                    continue

                meta = response.get("metadata") or {}
                latency = meta.get("latency_ms")
                think = meta.get("thinking_tokens")
                info(
                    f"  -> {len(response.get('sources') or [])} sources, "
                    f"{latency}ms, "
                    f"{think if think is not None else '-'} thinking tokens"
                )
                results.append(
                    QuestionResult(
                        id=q.id,
                        repetition=rep,
                        tier=q.tier,
                        bias=q.bias,
                        requested_collections=requested,
                        resolved_collection_ids=resolved,
                        reasoning_effort=effort,
                        text=q.text,
                        answer=response.get("answer", ""),
                        sources=response.get("sources") or [],
                        metadata=meta,
                    )
                )

    payload = {
        "started_at": started,
        "questions_path": str(qset.questions_path),
        "backend_url": args.base_url,
        "reasoning_effort": args.reasoning_effort,
        "repeat": args.repeat,
        "results": [asdict(r) for r in results],
    }
    out = Path(args.results_dir) / f"run-{started}.json"
    write_json(out, payload)
    info(f"\nwrote experiment results -> {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"rag2compare backend base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--questions", default=DEFAULT_QUESTIONS,
                   help=f"questions file path (default: {DEFAULT_QUESTIONS})")
    p.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR,
                   help=f"where to write run-<ts>.json (default: {DEFAULT_RESULTS_DIR})")
    p.add_argument("--reasoning-effort", default="xhigh",
                   choices=["off", "low", "medium", "high", "xhigh"],
                   help="Anthropic extended-thinking effort (default: xhigh)")
    p.add_argument("--collections", default=None,
                   help="comma-separated collection names to include "
                        "(others are stripped from each question's collection list)")
    p.add_argument("--repeat", type=int, default=1,
                   help="how many times to ask each question (default: 1)")
    p.add_argument("--only-tier", default=None,
                   help="if set, only run questions whose tier equals this string")
    p.add_argument("--only-id", default=None,
                   help="if set, only run the question with this id")
    p.add_argument("--dry-run", action="store_true",
                   help="print the planned questions without submitting")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
