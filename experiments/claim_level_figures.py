"""Recompute every claim-level figure the paper prints, as first reported
and as corrected (post-hoc, 2026-09).

The first claim-level run cut each cited passage to 1,500 characters
(run_claim_grounding.truncate). rescore_claim_grounding.py re-judged the
same claims on full passages and records both verdicts on every row:
original_verdict (the first run) and verdict (full passages). This script
reads those rows, so the first-reported figures are reproduced from the
same file as the corrected ones.

Definitions follow the paper. A main-arm claim is cited when
cited_source_idx is non-empty; a decomp-arm claim is cited when its
citation resolves to a chunk (n_cited_chunks > 0). Uncited claims count as
unsupported in the all-claims view. Macro rates average the per-question
rates over questions.

    python3 experiments/claim_level_figures.py \
        --main  experiments/results/post-hoc/rescore-main-capnone-20260928T113149Z.json \
        --decomp experiments/results/post-hoc/rescore-decomp-capnone-20260928T201439Z.json
"""
import argparse
import collections
import json

VERDICTS = ["supported", "partial", "contradicted", "unsupported"]
TIERS = ["bias-check", "chronological", "conflict", "emergence", "multi-hop", "policy"]


def pct(n, d):
    return 100.0 * n / d if d else float("nan")


def report(rows, is_cited, key, label):
    print(f"\n== {label}")
    for system in sorted({r["system"] for r in rows}):
        rs = [r for r in rows if r["system"] == system]
        cited = [r for r in rs if is_cited(r)]
        counts = collections.Counter(r[key] for r in cited)
        n, nc = len(rs), len(cited)
        all_unsup = (n - nc) + counts["unsupported"]
        print(f"[{system}] claims {n}, cited {nc}")
        print("  cited:     " + "  ".join(
            f"{v} {pct(counts[v], nc):.1f}% ({counts[v]})" for v in VERDICTS))
        print(f"  all-claims: supported {pct(counts['supported'], n):.1f}%"
              f"  unsupported {pct(all_unsup, n):.1f}%")
        byq = collections.defaultdict(list)
        for r in cited:
            byq[r["qid"]].append(r[key])
        for v in ("supported", "unsupported"):
            m = sum(pct(sum(x == v for x in l), len(l)) for l in byq.values()) / len(byq)
            print(f"  macro {v}: {m:.1f}%")
        byt = collections.defaultdict(list)
        for r in cited:
            byt[r["tier"]].append(r[key])
        for t in TIERS:
            l = byt[t]
            print(f"    {t:<14} n={len(l):3d}  " + "  ".join(
                f"{v[:5]} {pct(sum(x == v for x in l), len(l)):5.1f}" for v in VERDICTS))
        print("  contradicted:", [(r["qid"], r["claim_idx"]) for r in cited
                                  if r[key] == "contradicted"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--main", required=True)
    ap.add_argument("--decomp", required=True)
    a = ap.parse_args()
    main_rows = json.load(open(a.main))["rows"]
    decomp_rows = json.load(open(a.decomp))["rows"]
    main_cited = lambda r: bool(r["cited_source_idx"])
    decomp_cited = lambda r: r.get("n_cited_chunks", 0) > 0
    for key, label in (("original_verdict", "as first reported"),
                       ("verdict", "corrected, full passages")):
        report(main_rows, main_cited, key, f"main arms, {label}")
        report(decomp_rows, decomp_cited, key, f"decomp arm, {label}")


if __name__ == "__main__":
    main()
