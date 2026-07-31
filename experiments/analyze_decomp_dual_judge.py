"""Re-analyze the exploratory decomp-RAG ablation (§6) with two judges.

The decomp arm was originally scored by gpt-5.4 alone, while every other
result in the paper is dual-judge. This script consumes a decomp judged-*.json
that carries a `secondary` block (gemini/gemini-2.5-pro, same prompt, rubric,
and seed) and reports the §6 numbers under each judge separately and under the
preregistered judge-average, alongside the same quantities for the single-round
RAG baseline from the original judge run.

Everything here is exploratory: the H1/H2 subsets and the max-delta > 2 IRR
adjustment rule are reused from the preregistration so the ablation is read on
the same scale as the confirmatory analysis, not because the ablation is a
registered re-test.

Run:
    python experiments/analyze_decomp_dual_judge.py \
        --decomp-judged experiments/results/post-hoc/judged-<ts>.json
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"

ORIGINAL_JUDGED = RESULTS / "judged-20260506T225645Z.json"

H1_QIDS = [
    "T3-mia-as-copyright-evidence",
    "T3-rwd-validity-for-side-effects",
    "T4-cross-domain-audit",
    "T4-eelgrass-mrv-gaps",
]
H2_QIDS = [
    "B1-devote3-confidence-interval",
    "B2-he-tyka-equilibration-ratios",
    "B3-mia-attack-success-rate",
]
CRITS = ["groundedness", "structural_integrity", "conflict_awareness", "inter_paper_mapping"]
IRR_THRESHOLD = 2  # preregistered: max delta > 2 fires the judge-average adjustment


def load_judged(path):
    """Return (primary_by_qid, secondary_by_qid). Secondary may be empty."""
    with open(path) as f:
        j = json.load(f)
    primary = {x["question_id"]: x for x in j["judgments"]}
    sec = j.get("secondary") or {}
    secondary = {x["question_id"]: x for x in sec.get("judgments", [])}
    return j, primary, secondary


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def arm_mean(judgments, qids, crit, system):
    return mean([judgments[q][f"{system}_scores"][crit] for q in qids])


def judge_avg_mean(primary, secondary, qids, crit, system):
    return mean(
        [
            (primary[q][f"{system}_scores"][crit] + secondary[q][f"{system}_scores"][crit]) / 2
            for q in qids
        ]
    )


def max_delta(primary, secondary, crit, qids=None):
    qids = qids or sorted(set(primary) & set(secondary))
    deltas = [
        abs(primary[q][f"{s}_scores"][crit] - secondary[q][f"{s}_scores"][crit])
        for q in qids
        for s in ("rag", "wiki")
    ]
    return max(deltas) if deltas else None


def mean_abs_delta(primary, secondary, crit, qids=None):
    qids = qids or sorted(set(primary) & set(secondary))
    deltas = [
        abs(primary[q][f"{s}_scores"][crit] - secondary[q][f"{s}_scores"][crit])
        for q in qids
        for s in ("rag", "wiki")
    ]
    return mean(deltas)


def rule(label, width=76):
    print("\n" + "=" * width)
    print(label)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--decomp-judged", required=True, type=Path)
    ap.add_argument("--original-judged", default=ORIGINAL_JUDGED, type=Path)
    args = ap.parse_args()

    d_meta, d_pri, d_sec = load_judged(args.decomp_judged)
    o_meta, o_pri, o_sec = load_judged(args.original_judged)

    if not d_sec:
        raise SystemExit(f"no secondary judgments in {args.decomp_judged}")

    print(f"decomp judged:   {args.decomp_judged}")
    print(f"  primary:       {d_meta['judge_model']}  (effort={d_meta['reasoning_effort']}, seed={d_meta['seed']})")
    print(f"  secondary:     {d_meta['secondary']['judge_model']}  n={len(d_sec)}")
    print(f"original judged: {args.original_judged}")
    print(f"  primary:       {o_meta['judge_model']}  secondary: {o_meta['secondary']['judge_model']}")

    errored = [q for q, j in d_sec.items() if j.get("error")]
    if errored:
        print(f"\n  WARNING: secondary judgments with errors: {errored}")

    # ------------------------------------------------------------------
    # IRR for the ablation — does the preregistered adjustment rule fire?
    # ------------------------------------------------------------------
    rule("IRR on the decomp arm (max |gpt-5.4 - gemini| over question x system)")
    print(f"\n  {'criterion':<24}{'max delta':>10}{'mean |delta|':>14}   rule")
    for c in CRITS:
        md = max_delta(d_pri, d_sec, c)
        mad = mean_abs_delta(d_pri, d_sec, c)
        flag = "fires (> 2)" if md > IRR_THRESHOLD else "does not fire"
        print(f"  {c:<24}{md:>10}{mad:>14.3f}   {flag}")
    print("\n  Same statistic on the original judge run, for comparison:")
    for c in CRITS:
        md = max_delta(o_pri, o_sec, c)
        mad = mean_abs_delta(o_pri, o_sec, c)
        print(f"  {c:<24}{md:>10}{mad:>14.3f}")

    # ------------------------------------------------------------------
    # H1 subset — the ~88% gap-closure claim
    # ------------------------------------------------------------------
    rule("H1 confirmatory subset (n=4): wiki - RAG, single-round vs decomp")
    for crit in ("inter_paper_mapping", "structural_integrity"):
        print(f"\n  {crit}")
        print(f"    {'judge':<22}{'single':>9}{'decomp':>9}{'wiki(orig)':>12}{'wiki(dec)':>11}"
              f"{'gap single':>12}{'gap decomp':>12}{'closed':>9}")
        rows = [
            ("gpt-5.4 (primary)", o_pri, d_pri, None),
            ("gemini-2.5-pro", o_sec, d_sec, None),
            ("judge-average", None, None, True),
        ]
        for label, o_j, d_j, is_avg in rows:
            if is_avg:
                single = judge_avg_mean(o_pri, o_sec, H1_QIDS, crit, "rag")
                decomp = judge_avg_mean(d_pri, d_sec, H1_QIDS, crit, "rag")
                wiki_o = judge_avg_mean(o_pri, o_sec, H1_QIDS, crit, "wiki")
                wiki_d = judge_avg_mean(d_pri, d_sec, H1_QIDS, crit, "wiki")
            else:
                single = arm_mean(o_j, H1_QIDS, crit, "rag")
                decomp = arm_mean(d_j, H1_QIDS, crit, "rag")
                wiki_o = arm_mean(o_j, H1_QIDS, crit, "wiki")
                wiki_d = arm_mean(d_j, H1_QIDS, crit, "wiki")
            # Gap is measured within each judge run, so the wiki side comes from
            # the same run as the RAG arm it is compared against.
            gap_single = wiki_o - single
            gap_decomp = wiki_d - decomp
            closed = (1 - gap_decomp / gap_single) * 100 if gap_single else float("nan")
            print(f"    {label:<22}{single:>9.2f}{decomp:>9.2f}{wiki_o:>12.2f}{wiki_d:>11.2f}"
                  f"{gap_single:>+12.2f}{gap_decomp:>+12.2f}{closed:>8.1f}%")

        print("    per-question wiki - decomp (judge-average):", [
            round(
                (d_pri[q]["wiki_scores"][crit] + d_sec[q]["wiki_scores"][crit]) / 2
                - (d_pri[q]["rag_scores"][crit] + d_sec[q]["rag_scores"][crit]) / 2,
                2,
            )
            for q in H1_QIDS
        ])

    # ------------------------------------------------------------------
    # Groundedness and H2 parity, decomp vs wiki
    # ------------------------------------------------------------------
    rule("Decomp - wiki on groundedness (all 13) and H2 bias-check parity (n=3)")
    all_qids = sorted(set(d_pri) & set(d_sec))
    multi_hop = [q for q in all_qids if d_pri[q]["tier"] == "multi-hop"]
    for label, qids in (("all 13", all_qids), ("multi-hop", multi_hop), ("bias-check (H2)", H2_QIDS)):
        row = []
        for jl, p, s in (("gpt-5.4", d_pri, None), ("gemini", d_sec, None), ("judge-avg", d_pri, d_sec)):
            if s is None:
                diff = arm_mean(p, qids, "groundedness", "rag") - arm_mean(p, qids, "groundedness", "wiki")
            else:
                diff = judge_avg_mean(p, s, qids, "groundedness", "rag") - judge_avg_mean(
                    p, s, qids, "groundedness", "wiki"
                )
            row.append(f"{jl}={diff:+.2f}")
        print(f"  {label:<18}n={len(qids):<3} decomp - wiki: " + "  ".join(row))

    # ------------------------------------------------------------------
    # Cross-run wiki drift — same wiki answers, scored in two judge runs
    # ------------------------------------------------------------------
    rule("Cross-run wiki drift (identical wiki answers, original vs decomp judge run)")
    print(f"\n  {'criterion':<24}{'gpt all13':>11}{'gem all13':>11}{'avg all13':>11}"
          f"{'gpt H1':>9}{'gem H1':>9}{'avg H1':>9}   max |per-q|")
    for c in CRITS:
        cells = []
        for qids in (all_qids, H1_QIDS):
            cells.append(arm_mean(d_pri, qids, c, "wiki") - arm_mean(o_pri, qids, c, "wiki"))
            cells.append(arm_mean(d_sec, qids, c, "wiki") - arm_mean(o_sec, qids, c, "wiki"))
            cells.append(
                judge_avg_mean(d_pri, d_sec, qids, c, "wiki")
                - judge_avg_mean(o_pri, o_sec, qids, c, "wiki")
            )
        per_q = max(
            abs(d[q]["wiki_scores"][c] - o[q]["wiki_scores"][c])
            for d, o in ((d_pri, o_pri), (d_sec, o_sec))
            for q in all_qids
        )
        order = [cells[0], cells[1], cells[2], cells[3], cells[4], cells[5]]
        print(f"  {c:<24}" + "".join(
            f"{v:>+11.2f}" if i < 3 else f"{v:>+9.2f}" for i, v in enumerate(order)
        ) + f"{per_q:>14}")

    # ------------------------------------------------------------------
    # Full per-criterion means, both arms, both judges
    # ------------------------------------------------------------------
    rule("Overall means (all 13), decomp judge run")
    print(f"\n  {'criterion':<24}{'decomp gpt':>12}{'decomp gem':>12}{'decomp avg':>12}"
          f"{'wiki gpt':>10}{'wiki gem':>10}{'wiki avg':>10}")
    for c in CRITS:
        print(
            f"  {c:<24}"
            f"{arm_mean(d_pri, all_qids, c, 'rag'):>12.2f}"
            f"{arm_mean(d_sec, all_qids, c, 'rag'):>12.2f}"
            f"{judge_avg_mean(d_pri, d_sec, all_qids, c, 'rag'):>12.2f}"
            f"{arm_mean(d_pri, all_qids, c, 'wiki'):>10.2f}"
            f"{arm_mean(d_sec, all_qids, c, 'wiki'):>10.2f}"
            f"{judge_avg_mean(d_pri, d_sec, all_qids, c, 'wiki'):>10.2f}"
        )


if __name__ == "__main__":
    main()
