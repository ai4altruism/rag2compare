"""Claim-level grounding analysis (post-hoc, exploratory).

For each of the 26 (question, system) answer cells, decompose the answer into
atomic factual claims using Claude Opus 4.7, then score each claim's support
against its cited passage(s) using GPT-5.4 (cross-family from the answer model,
matching the main rubric-judge family).

Two-stage to keep atomization and scoring decoupled: atomization output is
cached so scoring can be re-run independently.

Output: experiments/results/grounding-<ts>.json containing per-claim verdicts
and aggregate statistics by system and tier.

Usage:
    . /tmp/prereg_env/bin/activate   # has anthropic + openai installed
    python experiments/run_claim_grounding.py [--atomize-only|--score-only|--cached]

Cost estimate: ~$2 USD on Opus 4.7 + GPT-5.4 at medium reasoning.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
load_dotenv(ROOT / ".env")

ANTHROPIC = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
OPENAI = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

ATOMIZER_MODEL = "claude-opus-4-7"
SCORER_MODEL = "gpt-5.4"

ATOMIZE_SYSTEM = """You are a careful factual analyst. You decompose answers
into atomic factual claims so they can be checked individually against
their cited sources.

Rules:
- Each claim must express ONE specific factual assertion.
- Each claim must be self-contained: resolve pronouns and ambiguous references.
- Faithfully paraphrase or quote what the answer says — do not infer beyond it.
- Skip pure framing, hedges, and meta-commentary that do not assert facts
  (e.g., "it is worth noting that", "the question is somewhat ambiguous").
- For each claim, list the 0-based indices of the SOURCES the answer
  explicitly cites for that claim. If the answer cites a filename, page,
  or source label, match it to the corresponding numbered source. If the
  claim is uncited (no source attribution in the answer), use [].
- A meta-claim about absence of information (e.g., "the corpus does not
  contain X") gets cited_source_idx = [] regardless of what sources were
  retrieved.

Output ONLY a JSON array. No prose, no markdown fence."""

SCORE_SYSTEM = """You are a careful factual evaluator. Given a CLAIM and
the cited PASSAGES from the answer's sources, decide whether the claim is
supported by the passages.

Categories (pick exactly one):
- supported: every factual element of the claim is explicitly stated or
  unambiguously implied by the passages.
- partial: some elements of the claim are supported by the passages, but
  others go beyond what the passages say (extrapolation, paraphrase that
  introduces new content, or unstated quantities).
- contradicted: the passages directly contradict the claim (state the
  opposite, give a different number, or assert the claim is false).
- unsupported: the claim is not addressed by the passages at all, OR no
  passages were cited (cited_source_idx = []).

Be strict on the supported/partial boundary: any element of the claim that
goes beyond the passages — even a small extrapolation — should drop it
to partial. Only mark contradicted when the passages explicitly disagree.

Output ONLY a JSON object: {"verdict": "supported|partial|contradicted|unsupported", "reason": "1-2 sentences"}.
No prose, no markdown fence."""


def truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "..."


def call_anthropic_atomize(answer: str, sources: list[dict]) -> list[dict]:
    """Atomize answer into claims with source citations. Returns list of claims."""
    numbered = []
    for i, s in enumerate(sources):
        ct = truncate(s.get("chunk_text", ""), 600)
        page = s.get("page_numbers", [])
        numbered.append(f"[{i}] {s['filename']} (p. {page}): {ct}")
    src_block = "\n\n".join(numbered)
    user = (
        f"ANSWER:\n{answer}\n\n"
        f"NUMBERED SOURCES (0-based):\n{src_block}\n\n"
        "Output the JSON array of claims now."
    )
    resp = ANTHROPIC.messages.create(
        model=ATOMIZER_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive", "display": "summarized"},
        extra_body={"output_config": {"effort": "medium"}},
        system=ATOMIZE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text_blocks = [b.text for b in resp.content if b.type == "text"]
    raw = "\n".join(text_blocks).strip()
    raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
    claims = json.loads(raw)
    for c in claims:
        c.setdefault("cited_source_idx", [])
    return claims


def call_openai_score(claim: str, cited_chunks: list[str]) -> dict:
    """Score one claim against its cited passages. Returns {verdict, reason}."""
    if not cited_chunks:
        passages = "(no passages cited for this claim)"
    else:
        passages = "\n\n".join(f"--- passage {i} ---\n{truncate(c, 1500)}" for i, c in enumerate(cited_chunks))
    user = f"CLAIM:\n{claim}\n\nCITED PASSAGES:\n{passages}"
    resp = OPENAI.chat.completions.create(
        model=SCORER_MODEL,
        messages=[
            {"role": "system", "content": SCORE_SYSTEM},
            {"role": "user", "content": user},
        ],
        reasoning_effort="medium",
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    obj = json.loads(raw)
    if obj.get("verdict") not in {"supported", "partial", "contradicted", "unsupported"}:
        obj["verdict"] = "unsupported"
    return obj


def safe_call(fn, *args, max_retries=3, **kwargs):
    last = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last = e
            sleep = 2 ** attempt
            print(f"  [retry {attempt+1}/{max_retries} after {sleep}s] {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            time.sleep(sleep)
    raise last


def atomize_all(rag_run, wiki_run) -> dict:
    """Returns {qid: {system: {answer, sources, claims}}}."""
    out = {}
    n_total = 26
    n_done = 0
    for label, run in [("rag", rag_run), ("wiki", wiki_run)]:
        for r in run["results"]:
            qid = r["id"]
            answer = r["answer"]
            sources = r["sources"]
            n_done += 1
            print(f"[atomize {n_done}/{n_total}] {label:<5} {qid}  (answer={len(answer)}c, n_src={len(sources)})", flush=True)
            claims = safe_call(call_anthropic_atomize, answer, sources)
            out.setdefault(qid, {})[label] = {
                "answer_len": len(answer),
                "n_sources": len(sources),
                "claims": claims,
            }
            print(f"    -> {len(claims)} claims", flush=True)
    return out


def score_all(atomized: dict, run_artifacts: dict) -> list[dict]:
    """Returns list of {qid, system, claim_idx, claim, cited_idx, verdict, reason}."""
    scored = []
    n_total = sum(len(s["claims"]) for q in atomized.values() for s in q.values())
    n_done = 0
    for qid, by_system in atomized.items():
        for system, data in by_system.items():
            sources = run_artifacts[system][qid]["sources"]
            for ci, claim in enumerate(data["claims"]):
                idx = claim.get("cited_source_idx", [])
                cited_chunks = []
                for i in idx:
                    if 0 <= i < len(sources):
                        ct = sources[i].get("chunk_text", "")
                        if ct:
                            cited_chunks.append(ct)
                n_done += 1
                if n_done % 25 == 0 or n_done == 1:
                    print(f"[score {n_done}/{n_total}] {system:<5} {qid} #{ci}  (n_chunks={len(cited_chunks)})", flush=True)
                v = safe_call(call_openai_score, claim["claim"], cited_chunks)
                scored.append({
                    "qid": qid,
                    "system": system,
                    "claim_idx": ci,
                    "claim": claim["claim"],
                    "cited_source_idx": idx,
                    "n_cited_chunks": len(cited_chunks),
                    "verdict": v["verdict"],
                    "reason": v["reason"],
                })
    return scored


def aggregate(scored: list[dict], primary_judgments: dict) -> dict:
    by_system = {"rag": {}, "wiki": {}}
    by_tier = {}
    for system in ["rag", "wiki"]:
        rows = [r for r in scored if r["system"] == system]
        n = len(rows)
        verdicts = [r["verdict"] for r in rows]
        cited = [r for r in rows if r["n_cited_chunks"] > 0]
        by_system[system] = {
            "n_claims": n,
            "n_cited": len(cited),
            "cited_rate": len(cited) / n if n else 0.0,
            "supported_rate": verdicts.count("supported") / n if n else 0.0,
            "partial_rate": verdicts.count("partial") / n if n else 0.0,
            "contradicted_rate": verdicts.count("contradicted") / n if n else 0.0,
            "unsupported_rate": verdicts.count("unsupported") / n if n else 0.0,
            "supported_or_partial_rate": (verdicts.count("supported") + verdicts.count("partial")) / n if n else 0.0,
            "n_supported": verdicts.count("supported"),
            "n_partial": verdicts.count("partial"),
            "n_contradicted": verdicts.count("contradicted"),
            "n_unsupported": verdicts.count("unsupported"),
        }

    for r in scored:
        tier = primary_judgments[r["qid"]]["tier"]
        by_tier.setdefault(tier, {"rag": [], "wiki": []})
        by_tier[tier][r["system"]].append(r["verdict"])

    by_tier_summary = {}
    for tier, data in by_tier.items():
        by_tier_summary[tier] = {}
        for system in ["rag", "wiki"]:
            v = data[system]
            n = len(v)
            by_tier_summary[tier][system] = {
                "n_claims": n,
                "supported_rate": v.count("supported") / n if n else 0.0,
                "unsupported_rate": v.count("unsupported") / n if n else 0.0,
                "contradicted_rate": v.count("contradicted") / n if n else 0.0,
            }
    return {"overall": by_system, "by_tier": by_tier_summary}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", action="store_true", help="reuse cached atomization/scoring")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with open(RESULTS / "run-20260506T221602Z.json") as f:
        rag_run = json.load(f)
    with open(RESULTS / "wiki-run-20260506T205500Z.json") as f:
        wiki_run = json.load(f)
    with open(RESULTS / "judged-20260506T225645Z.json") as f:
        judged = json.load(f)
    primary_judgments = {x["question_id"]: x for x in judged["judgments"]}

    cache_atomize = RESULTS / "grounding-atomize-cache.json"
    cache_score = RESULTS / "grounding-score-cache.json"

    if args.cached and cache_atomize.exists():
        with open(cache_atomize) as f:
            atomized = json.load(f)
        print(f"[loaded atomization cache: {sum(len(s['claims']) for q in atomized.values() for s in q.values())} claims]")
    else:
        atomized = atomize_all(rag_run, wiki_run)
        with open(cache_atomize, "w") as f:
            json.dump(atomized, f, indent=2)
        print(f"[saved atomization cache to {cache_atomize}]")

    run_artifacts = {
        "rag": {r["id"]: r for r in rag_run["results"]},
        "wiki": {r["id"]: r for r in wiki_run["results"]},
    }

    if args.cached and cache_score.exists():
        with open(cache_score) as f:
            scored = json.load(f)
        print(f"[loaded scoring cache: {len(scored)} judgments]")
    else:
        scored = score_all(atomized, run_artifacts)
        with open(cache_score, "w") as f:
            json.dump(scored, f, indent=2)
        print(f"[saved scoring cache to {cache_score}]")

    agg = aggregate(scored, primary_judgments)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else RESULTS / f"grounding-{ts}.json"
    with open(out_path, "w") as f:
        json.dump({
            "atomizer_model": ATOMIZER_MODEL,
            "scorer_model": SCORER_MODEL,
            "rag_run": "run-20260506T221602Z.json",
            "wiki_run": "wiki-run-20260506T205500Z.json",
            "atomized": atomized,
            "scored": scored,
            "aggregate": agg,
            "generated_at": ts,
        }, f, indent=2)
    print(f"\n[saved combined output to {out_path}]")

    # Print summary
    print("\n=== AGGREGATE BY SYSTEM ===")
    for system in ["rag", "wiki"]:
        a = agg["overall"][system]
        print(f"\n  {system.upper()}: n_claims={a['n_claims']}, n_cited={a['n_cited']} ({100*a['cited_rate']:.1f}%)")
        print(f"    supported:    {a['n_supported']:>3} ({100*a['supported_rate']:.1f}%)")
        print(f"    partial:      {a['n_partial']:>3} ({100*a['partial_rate']:.1f}%)")
        print(f"    contradicted: {a['n_contradicted']:>3} ({100*a['contradicted_rate']:.1f}%)")
        print(f"    unsupported:  {a['n_unsupported']:>3} ({100*a['unsupported_rate']:.1f}%)")

    print("\n=== BY TIER ===")
    print(f"{'tier':<14} {'sys':<5} {'n':>4} {'sup%':>6} {'unsup%':>7} {'cont%':>6}")
    for tier, byt in agg["by_tier"].items():
        for system in ["rag", "wiki"]:
            d = byt[system]
            print(f"{tier:<14} {system:<5} {d['n_claims']:>4} {100*d['supported_rate']:>5.1f}% {100*d['unsupported_rate']:>6.1f}% {100*d['contradicted_rate']:>5.1f}%")


if __name__ == "__main__":
    main()
