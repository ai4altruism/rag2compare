"""Run claim-level grounding on the decomp-RAG ablation answers.

Reuses run_claim_grounding.py's helpers. Atomises the decomp answers with
Opus 4.7 and scores each cited claim with cross-family GPT-5.4 against the
chunks the decomp pipeline cited. Output mirrors the original
grounding-*.json schema so analysis is uniform across all three systems.

Usage:
    . /tmp/prereg_env/bin/activate
    python experiments/run_claim_grounding_decomp.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_claim_grounding import (
    safe_call, call_anthropic_atomize, call_openai_score,
    ATOMIZER_MODEL, SCORER_MODEL,
)

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
DECOMP_RUN = RESULTS / "run-decomp-20260509T001618Z.json"


def main():
    with open(DECOMP_RUN) as f:
        decomp = json.load(f)

    atomized = []
    print(f"=== ATOMISATION (decomp, n={len(decomp['results'])}) ===", flush=True)
    for i, r in enumerate(decomp["results"]):
        qid = r["id"]
        ans = r["answer"]
        srcs = r["sources"]
        print(f"[atomise {i+1}/{len(decomp['results'])}] {qid}  (answer={len(ans)}c, n_src={len(srcs)})", flush=True)
        claims = safe_call(call_anthropic_atomize, ans, srcs)
        print(f"    -> {len(claims)} claims", flush=True)
        atomized.append({
            "qid": qid,
            "tier": r["tier"],
            "answer_len": len(ans),
            "n_sources": len(srcs),
            "claims": claims,
            "sources": srcs,
        })

    cache_a = RESULTS / "grounding-decomp-atomize-cache.json"
    with open(cache_a, "w") as f:
        json.dump(atomized, f, indent=2)
    print(f"\n[saved atomisation cache to {cache_a}]\n", flush=True)

    scored = []
    n_total = sum(len(q["claims"]) for q in atomized)
    n_done = 0
    print(f"=== SCORING (decomp, n_claims={n_total}) ===", flush=True)
    for q in atomized:
        srcs = q["sources"]
        for ci, c in enumerate(q["claims"]):
            idx = c.get("cited_source_idx", [])
            cited_chunks = []
            for i in idx:
                if 0 <= i < len(srcs):
                    ct = srcs[i].get("chunk_text", "")
                    if ct:
                        cited_chunks.append(ct)
            n_done += 1
            if n_done % 25 == 0 or n_done == 1:
                print(f"[score {n_done}/{n_total}] {q['qid']} #{ci}  (n_chunks={len(cited_chunks)})", flush=True)
            v = safe_call(call_openai_score, c["claim"], cited_chunks)
            scored.append({
                "qid": q["qid"],
                "tier": q["tier"],
                "system": "decomp",
                "claim_idx": ci,
                "claim": c["claim"],
                "cited_source_idx": idx,
                "n_cited_chunks": len(cited_chunks),
                "verdict": v["verdict"],
                "reason": v["reason"],
            })

    cache_s = RESULTS / "grounding-decomp-score-cache.json"
    with open(cache_s, "w") as f:
        json.dump(scored, f, indent=2)
    print(f"\n[saved scoring cache to {cache_s}]", flush=True)

    # Aggregate
    from collections import Counter, defaultdict
    overall_v = [s["verdict"] for s in scored]
    cited = [s for s in scored if s["n_cited_chunks"] > 0]
    cited_v = [s["verdict"] for s in cited]
    n = len(scored)
    nc = len(cited)

    def pct(v, total):
        return (Counter(v).get("supported", 0)/total*100,
                Counter(v).get("partial", 0)/total*100,
                Counter(v).get("contradicted", 0)/total*100,
                Counter(v).get("unsupported", 0)/total*100)

    print(f"\n=== AGGREGATE (decomp, n={n} claims) ===")
    s, p, c, u = pct(overall_v, n)
    print(f"  all claims:   sup={s:.1f}% part={p:.1f}% cont={c:.1f}% unsup={u:.1f}%")
    s, p, c, u = pct(cited_v, nc)
    print(f"  cited only (n={nc}, {nc/n*100:.1f}% cited): sup={s:.1f}% part={p:.1f}% cont={c:.1f}% unsup={u:.1f}%")

    print(f"\n=== BY TIER (cited only) ===")
    by_tier = defaultdict(list)
    for s in cited:
        by_tier[s["tier"]].append(s["verdict"])
    print(f"{'tier':<14} {'n':>3}  sup%   part%  unsup%  cont%")
    for t in sorted(by_tier):
        v = by_tier[t]; nn = len(v); sp, pp, cp, up = pct(v, nn)
        print(f"{t:<14} {nn:>3}  {sp:>4.1f}%  {pp:>4.1f}%  {up:>4.1f}%  {cp:>4.1f}%")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS / f"grounding-decomp-{ts}.json"
    with open(out_path, "w") as f:
        json.dump({
            "atomizer_model": ATOMIZER_MODEL,
            "scorer_model": SCORER_MODEL,
            "decomp_run": DECOMP_RUN.name,
            "n_claims": n,
            "n_cited": nc,
            "atomized": atomized,
            "scored": scored,
        }, f, indent=2)
    print(f"\n[saved combined output to {out_path}]")


if __name__ == "__main__":
    main()
