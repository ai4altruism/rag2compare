"""Decomposition-based RAG ablation (post-hoc, exploratory).

Tests the reviewer hypothesis: is the LLM Wiki advantage on inter_paper_mapping
because RAG is too simple? We decompose each question into 2-5 sub-questions,
retrieve via the existing single-round RAG pipeline per sub-question, deduplicate
the cited chunks, and generate the final answer against the aggregated context.

Pipeline shape:
    question
      -> Anthropic Opus 4.7 (decomposer): 2-5 sub-questions in JSON
      -> for each sub-question: POST /api/query (single-round RAG)
                                keep `sources`, discard the per-sub answer
      -> dedupe cited chunks by (filename, chunk_text)
      -> Anthropic Opus 4.7 (final answer generator):
            system = backend's DEFAULT_SYSTEM_PROMPT (verbatim)
            user   = "Context chunks:\n\n<numbered>\n\nQuestion: <original>"

Output: experiments/results/run-decomp-<ts>.json with the same per-question
schema as run-*.json (id, tier, bias, text, answer, sources, metadata) so
the existing judge pipeline can consume it directly. Extra fields under
metadata.decomposition / metadata.retrieval_per_subq / metadata.final_answer
preserve the staged telemetry.

Usage:
    docker compose up -d                                     # backend must be up
    . /tmp/prereg_env/bin/activate
    python experiments/run_decomp_rag.py                     # full run
    python experiments/run_decomp_rag.py --only-id T3-rwd-validity-for-side-effects
                                                             # smoke on one question

Cost estimate: ~$15-25 USD for the 13-question run (decomposition + N x retrieval
+ final answer per question).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
QUESTIONS_PATH = ROOT / "experiments" / "questions.yaml"
load_dotenv(ROOT / ".env")

DEFAULT_BASE_URL = "http://localhost:8000"
ANSWER_MODEL = "claude-opus-4-7"
DEFAULT_REASONING_EFFORT = "xhigh"
DECOMP_REASONING_EFFORT = "medium"  # Decomposition is mechanical, save spend.

ANTHROPIC = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Verbatim from backend/src/pipelines/query/generator.py:DEFAULT_SYSTEM_PROMPT.
# Kept in sync so the decomp-RAG final answer is generated under the same
# instructions as the single-round RAG baseline.
ANSWER_SYSTEM_PROMPT = """\
You are a helpful research assistant. Answer the user's question based ONLY on the \
provided context chunks. Follow these rules strictly:

1. Only use information from the provided context to answer.
2. Cite your sources using [Source N] notation, where N corresponds to the chunk number.
3. If the context does not contain enough information to answer the question, say so \
clearly — do NOT make up or infer information beyond what is provided.
4. Be concise and precise. Prefer direct answers over lengthy explanations.
5. If the question asks about something not covered in the context, respond: \
"The provided documents do not contain sufficient information to answer this question."
"""

DECOMP_SYSTEM_PROMPT = """\
You are a careful research analyst. Given a research question, decompose it into \
2 to 5 sub-questions whose answers, taken together, would let a well-informed reader \
answer the original question.

Rules:
- Each sub-question must be self-contained and answerable from a research-paper \
corpus (no pronoun references back to the original).
- Sub-questions should not overlap heavily; each should target a distinct piece of \
evidence the original needs.
- If the original is a simple point-source lookup ("what was the confidence interval \
in DEVOTE 3?"), still produce 2-3 sub-questions that target adjacent context the \
answer should cite.
- Do NOT answer the original question. Only emit the sub-question list.

Output ONLY a JSON array of strings: ["sub-q 1", "sub-q 2", ...]. No prose, no markdown."""


@dataclass
class SubQRetrieval:
    sub_question: str
    n_sources: int
    prompt_tokens: int
    completion_tokens: int
    thinking_tokens: int
    latency_ms: int
    error: str | None = None


@dataclass
class QuestionResult:
    id: str
    tier: str
    bias: str
    text: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: str | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_questions() -> list[dict]:
    with open(QUESTIONS_PATH) as f:
        data = yaml.safe_load(f)
    return data["questions"]


def health_check(client: httpx.Client) -> None:
    r = client.get("/api/health")
    r.raise_for_status()


def resolve_collections(client: httpx.Client) -> dict[str, str]:
    r = client.get("/api/collections")
    r.raise_for_status()
    return {c["name"]: c["id"] for c in r.json()}


def call_decomposer(question_text: str) -> tuple[list[str], dict]:
    """Returns (sub_questions, telemetry_dict)."""
    t0 = time.time()
    resp = ANTHROPIC.messages.create(
        model=ANSWER_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive", "display": "summarized"},
        extra_body={"output_config": {"effort": DECOMP_REASONING_EFFORT}},
        system=DECOMP_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question_text}],
    )
    latency_ms = int((time.time() - t0) * 1000)
    text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    sub_qs = json.loads(text)
    if not isinstance(sub_qs, list) or not all(isinstance(x, str) for x in sub_qs):
        raise ValueError(f"decomposer returned non-list: {text[:200]}")
    if not (2 <= len(sub_qs) <= 5):
        raise ValueError(f"decomposer returned {len(sub_qs)} sub-questions; expected 2-5")
    usage = resp.usage
    telemetry = {
        "n_sub_questions": len(sub_qs),
        "prompt_tokens": getattr(usage, "input_tokens", 0),
        "completion_tokens": getattr(usage, "output_tokens", 0),
        "latency_ms": latency_ms,
    }
    return sub_qs, telemetry


def submit_subq(client: httpx.Client, sub_q: str, collection_ids: list[str]) -> dict:
    """POST /api/query for one sub-question. Returns the parsed response (or {} on error)."""
    payload = {
        "query": sub_q,
        "collection_ids": collection_ids,
        "options": {"reasoning_effort": DEFAULT_REASONING_EFFORT},
    }
    r = client.post("/api/query", json=payload)
    r.raise_for_status()
    return r.json()


def dedupe_sources(source_lists: list[list[dict]]) -> list[dict]:
    """Dedupe by (filename, chunk_text). Preserve first occurrence's full record."""
    seen = set()
    out = []
    for sl in source_lists:
        for s in sl:
            key = (s.get("filename", ""), s.get("chunk_text", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
    return out


def format_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        filename = c.get("filename", "unknown")
        pages = c.get("page_numbers", [])
        headers = c.get("header_chain", [])
        text = c.get("chunk_text", "")
        header = f"[Source {i}] {filename}"
        if pages:
            header += f" (p. {', '.join(str(p) for p in pages)})"
        if headers:
            header += f" — {' > '.join(headers)}"
        parts.append(f"{header}\n{text}")
    return "\n\n---\n\n".join(parts)


def call_final_answer(question_text: str, chunks: list[dict]) -> tuple[str, dict]:
    """Returns (answer_text, telemetry_dict)."""
    user = f"Context chunks:\n\n{format_context(chunks)}\n\nQuestion: {question_text}"
    t0 = time.time()
    resp = ANTHROPIC.messages.create(
        model=ANSWER_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive", "display": "summarized"},
        extra_body={"output_config": {"effort": DEFAULT_REASONING_EFFORT}},
        system=ANSWER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    latency_ms = int((time.time() - t0) * 1000)
    answer = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    usage = resp.usage
    thinking_tokens = 0
    for b in resp.content:
        if b.type == "thinking" and getattr(b, "thinking", ""):
            try:
                ct = ANTHROPIC.messages.count_tokens(
                    model=ANSWER_MODEL,
                    messages=[{"role": "user", "content": b.thinking}],
                )
                thinking_tokens += ct.input_tokens
            except Exception:
                pass
    telemetry = {
        "prompt_tokens": getattr(usage, "input_tokens", 0),
        "completion_tokens": getattr(usage, "output_tokens", 0),
        "thinking_tokens": thinking_tokens,
        "latency_ms": latency_ms,
    }
    return answer, telemetry


def run_one(client: httpx.Client, q: dict, name_to_id: dict[str, str]) -> QuestionResult:
    qid = q["id"]
    text = q["text"]
    tier = q["tier"]
    bias = q.get("bias", "neutral")
    requested = q.get("collections", [])
    collection_ids = [name_to_id[c] for c in requested if c in name_to_id]

    print(f"[{qid}] tier={tier} bias={bias}", flush=True)
    print(f"  decomposing...", flush=True)
    try:
        sub_qs, decomp_telemetry = call_decomposer(text)
    except Exception as e:
        return QuestionResult(id=qid, tier=tier, bias=bias, text=text, answer="",
                              error=f"decompose failed: {e}")
    print(f"    -> {len(sub_qs)} sub-questions ({decomp_telemetry['prompt_tokens']}p/{decomp_telemetry['completion_tokens']}c tok)", flush=True)
    for i, sq in enumerate(sub_qs):
        print(f"       [{i}] {sq[:120]}", flush=True)

    sub_retrievals = []
    source_lists = []
    for i, sq in enumerate(sub_qs):
        try:
            t0 = time.time()
            sub_resp = submit_subq(client, sq, collection_ids)
            latency_ms = int((time.time() - t0) * 1000)
            sources = sub_resp.get("sources", [])
            md = sub_resp.get("metadata", {}) or {}
            sub_retrievals.append(SubQRetrieval(
                sub_question=sq,
                n_sources=len(sources),
                prompt_tokens=md.get("prompt_tokens") or 0,
                completion_tokens=md.get("completion_tokens") or 0,
                thinking_tokens=md.get("thinking_tokens") or 0,
                latency_ms=latency_ms,
            ))
            source_lists.append(sources)
            print(f"  sub[{i}]: {len(sources)} sources, {md.get('prompt_tokens',0)}p tok, {latency_ms}ms", flush=True)
        except Exception as e:
            sub_retrievals.append(SubQRetrieval(
                sub_question=sq, n_sources=0, prompt_tokens=0, completion_tokens=0,
                thinking_tokens=0, latency_ms=0, error=f"{type(e).__name__}: {e}",
            ))
            source_lists.append([])
            print(f"  sub[{i}]: ERROR {e}", flush=True)

    deduped = dedupe_sources(source_lists)
    print(f"  aggregated -> {len(deduped)} unique chunks (from {sum(len(s) for s in source_lists)} retrievals)", flush=True)

    if not deduped:
        return QuestionResult(id=qid, tier=tier, bias=bias, text=text, answer="",
                              sources=[], error="no sources retrieved across sub-questions")

    print(f"  generating final answer...", flush=True)
    try:
        answer, final_telemetry = call_final_answer(text, deduped)
    except Exception as e:
        return QuestionResult(id=qid, tier=tier, bias=bias, text=text, answer="",
                              sources=deduped, error=f"final-answer failed: {e}")
    print(f"    -> answer={len(answer)} chars, {final_telemetry['prompt_tokens']}p/{final_telemetry['completion_tokens']}c/{final_telemetry['thinking_tokens']}th tok, {final_telemetry['latency_ms']}ms", flush=True)

    # Top-level metadata mirrors single-round RAG's run-*.json schema for judge compat
    total_prompt = decomp_telemetry["prompt_tokens"] + sum(s.prompt_tokens for s in sub_retrievals) + final_telemetry["prompt_tokens"]
    total_completion = decomp_telemetry["completion_tokens"] + sum(s.completion_tokens for s in sub_retrievals) + final_telemetry["completion_tokens"]
    total_thinking = sum(s.thinking_tokens for s in sub_retrievals) + final_telemetry["thinking_tokens"]
    total_latency = decomp_telemetry["latency_ms"] + sum(s.latency_ms for s in sub_retrievals) + final_telemetry["latency_ms"]

    return QuestionResult(
        id=qid, tier=tier, bias=bias, text=text, answer=answer,
        sources=deduped,
        metadata={
            "model_used": ANSWER_MODEL,
            "reasoning_effort": DEFAULT_REASONING_EFFORT,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "thinking_tokens": total_thinking,
            "latency_ms": total_latency,
            "decomposition": {
                "system_prompt": DECOMP_SYSTEM_PROMPT,
                "sub_questions": sub_qs,
                "telemetry": decomp_telemetry,
            },
            "retrieval_per_subq": [asdict(s) for s in sub_retrievals],
            "aggregation": {
                "n_unique_sources": len(deduped),
                "n_total_retrieved": sum(len(s) for s in source_lists),
            },
            "final_answer": final_telemetry,
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--only-id", help="run only this question id")
    parser.add_argument("--only-tier", help="run only this tier")
    parser.add_argument("--out", help="output path; default = experiments/results/run-decomp-<ts>.json")
    args = parser.parse_args()

    questions = load_questions()
    if args.only_id:
        questions = [q for q in questions if q["id"] == args.only_id]
    if args.only_tier:
        questions = [q for q in questions if q["tier"] == args.only_tier]
    if not questions:
        print("no questions matched filter", file=sys.stderr)
        return 1

    started = utc_timestamp()
    results: list[QuestionResult] = []
    with httpx.Client(base_url=args.base_url, timeout=600.0) as client:
        try:
            health_check(client)
        except Exception as e:
            print(f"backend health check failed: {e}", file=sys.stderr)
            print(f"is the docker stack up? -> docker compose up -d", file=sys.stderr)
            return 2
        name_to_id = resolve_collections(client)
        for q in questions:
            r = run_one(client, q, name_to_id)
            results.append(r)
            if r.error:
                print(f"  -> ERROR {r.error}\n", flush=True)
            else:
                print(f"  -> done\n", flush=True)

    finished = utc_timestamp()
    out_path = Path(args.out) if args.out else RESULTS / f"run-decomp-{finished}.json"
    payload = {
        "schema_version": "rag2compare.run-decomp.v1",
        "started_at": started,
        "finished_at": finished,
        "ablation": "decomposition-rag",
        "answer_model": ANSWER_MODEL,
        "decomposer_effort": DECOMP_REASONING_EFFORT,
        "answer_effort": DEFAULT_REASONING_EFFORT,
        "n_questions": len(results),
        "n_errors": sum(1 for r in results if r.error),
        "results": [asdict(r) for r in results],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n[saved {out_path}]", flush=True)

    # Summary
    total_p = sum(r.metadata.get("prompt_tokens", 0) for r in results if not r.error)
    total_c = sum(r.metadata.get("completion_tokens", 0) for r in results if not r.error)
    total_t = sum(r.metadata.get("thinking_tokens", 0) for r in results if not r.error)
    total_lat = sum(r.metadata.get("latency_ms", 0) for r in results if not r.error)
    print(f"\n=== Summary (n_ok={len(results) - sum(1 for r in results if r.error)}) ===")
    print(f"  total prompt tokens:     {total_p:,}")
    print(f"  total completion tokens: {total_c:,}")
    print(f"  total thinking tokens:   {total_t:,}")
    print(f"  total wall-clock:        {total_lat/1000/60:.1f} min")


if __name__ == "__main__":
    sys.exit(main() or 0)
