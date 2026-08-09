"""Conventional inter-judge agreement statistics, leave-one-question-out
sensitivity, and per-answer length telemetry.

Added for the TMLR submission in response to review feedback that the paper
used "IRR" mainly as shorthand for a max-delta trigger. Max-delta is a
worst-case statistic: one outlier cell moves it, and it says nothing about
whether the two judges rank systems the same way. This script computes the
agreement summaries a reader expects under that heading, plus two diagnostics
the same review asked for.

Everything here reads the deposited artifacts and adds no API calls, so it
reproduces offline from the OSF deposit alone. Deliberately dependency-free
(no numpy/scipy): the preregistered analysis needs pymc, but a reviewer
checking these numbers should not have to build an environment to do it.

Run:
    python experiments/analyze_irr_stats.py
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"

JUDGED = RESULTS / "judged-20260506T225645Z.json"
RAG_RUN = RESULTS / "run-20260506T221602Z.json"
WIKI_RUN = RESULTS / "wiki-run-20260506T205500Z.json"
GROUNDING = RESULTS / "grounding-20260508T155234Z.json"

# Registered subsets (mirrors run_preregistered_analysis.py).
H1_QIDS = ["T3-mia-as-copyright-evidence", "T3-rwd-validity-for-side-effects",
           "T4-cross-domain-audit", "T4-eelgrass-mrv-gaps"]
H2_TIER = "bias-check"

SCALE_MIN, SCALE_MAX = 1, 10


# --------------------------------------------------------------------------
# Small statistics library (stdlib only).
# --------------------------------------------------------------------------
def mean(xs):
    return sum(xs) / len(xs)


def ranks(xs):
    """Average ranks, ties shared."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def pearson(xs, ys):
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else float("nan")


def spearman(xs, ys):
    return pearson(ranks(xs), ranks(ys))


def kendall_tau_b(xs, ys):
    n = len(xs)
    conc = disc = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            p = dx * dy
            if p > 0:
                conc += 1
            elif p < 0:
                disc += 1
            else:
                if dx == 0 and dy != 0:
                    tx += 1
                elif dy == 0 and dx != 0:
                    ty += 1
                else:
                    tx += 1
                    ty += 1
    d = ((conc + disc + tx) * (conc + disc + ty)) ** 0.5
    return (conc - disc) / d if d else float("nan")


def quadratic_weighted_kappa(xs, ys, lo=SCALE_MIN, hi=SCALE_MAX):
    cats = list(range(lo, hi + 1))
    idx = {c: i for i, c in enumerate(cats)}
    n = len(cats)
    O = [[0] * n for _ in range(n)]
    for a, b in zip(xs, ys):
        O[idx[int(a)]][idx[int(b)]] += 1
    total = len(xs)
    rowsum = [sum(O[i]) for i in range(n)]
    colsum = [sum(O[i][j] for i in range(n)) for j in range(n)]
    denom_w = (n - 1) ** 2
    num = den = 0.0
    for i in range(n):
        for j in range(n):
            w = ((i - j) ** 2) / denom_w
            E = rowsum[i] * colsum[j] / total
            num += w * O[i][j]
            den += w * E
    return 1 - num / den if den else float("nan")


def icc_2_1(xs, ys):
    """Two-way random effects, absolute agreement, single measurement."""
    n, k = len(xs), 2
    grand = mean(xs + ys)
    subj_means = [(a + b) / 2.0 for a, b in zip(xs, ys)]
    rater_means = [mean(xs), mean(ys)]
    MSR = k * sum((m - grand) ** 2 for m in subj_means) / (n - 1)
    MSC = n * sum((m - grand) ** 2 for m in rater_means) / (k - 1)
    ss_e = 0.0
    for i, (a, b) in enumerate(zip(xs, ys)):
        for r, v in enumerate((a, b)):
            ss_e += (v - subj_means[i] - rater_means[r] + grand) ** 2
    MSE = ss_e / ((n - 1) * (k - 1))
    den = MSR + (k - 1) * MSE + k * (MSC - MSE) / n
    return (MSR - MSE) / den if den else float("nan")


# --------------------------------------------------------------------------
def load_judged():
    d = json.loads(JUDGED.read_text())
    prim = {j["question_id"]: j for j in d["judgments"]}
    sec = {j["question_id"]: j for j in d["secondary"]["judgments"]}
    return d, prim, sec


def paired_points(prim, sec, criteria):
    """(criterion) -> (primary_scores, secondary_scores) over 13 q x 2 arms."""
    out = {}
    for c in criteria:
        a, b = [], []
        for qid in sorted(prim):
            if qid not in sec:
                continue
            for arm in ("rag_scores", "wiki_scores"):
                pa, sb = prim[qid].get(arm), sec[qid].get(arm)
                if pa and sb and c in pa and c in sb:
                    a.append(pa[c])
                    b.append(sb[c])
        out[c] = (a, b)
    return out


def main():
    d, prim, sec = load_judged()
    criteria = d["criteria"]

    print("=" * 74)
    print("A. INTER-JUDGE AGREEMENT  (primary GPT-5.4 vs secondary Gemini 2.5 Pro)")
    print("=" * 74)
    pts = paired_points(prim, sec, criteria)
    print(f"{'criterion':<22}{'n':>4}{'rho':>8}{'tau_b':>8}{'QWK':>8}"
          f"{'ICC':>8}{'MAD':>8}{'bias':>8}")
    agreement_rows = {}
    for c in criteria:
        a, b = pts[c]
        rho = spearman(a, b)
        tau = kendall_tau_b(a, b)
        qwk = quadratic_weighted_kappa(a, b)
        icc = icc_2_1(a, b)
        mad = mean([abs(x - y) for x, y in zip(a, b)])
        bias = mean(b) - mean(a)          # secondary minus primary = level shift
        agreement_rows[c] = dict(n=len(a), rho=rho, tau=tau, qwk=qwk,
                                 icc=icc, mad=mad, bias=bias)
        print(f"{c:<22}{len(a):>4}{rho:>8.3f}{tau:>8.3f}{qwk:>8.3f}"
              f"{icc:>8.3f}{mad:>8.2f}{bias:>+8.2f}")

    print()
    print("  'bias' is mean(secondary) - mean(primary): positive = secondary")
    print("  scores higher overall. Separating it from rho/tau is the point:")
    print("  a large bias with high rho is calibration drift, not disagreement")
    print("  about which answer is better.")

    print()
    print("-" * 74)
    print("B. LEVEL vs RANKING  (does the shift survive removing the level?)")
    print("-" * 74)
    print(f"{'criterion':<22}{'n':>4}{'rho(delta)':>12}{'sign agree':>12}")
    for c in criteria:
        dp, ds = [], []
        for qid in sorted(prim):
            if qid not in sec:
                continue
            p, s = prim[qid], sec[qid]
            if not (p.get("wiki_scores") and p.get("rag_scores")
                    and s.get("wiki_scores") and s.get("rag_scores")):
                continue
            dp.append(p["wiki_scores"][c] - p["rag_scores"][c])
            ds.append(s["wiki_scores"][c] - s["rag_scores"][c])
        agree = sum(1 for x, y in zip(dp, ds)
                    if (x > 0) == (y > 0) or (x == 0 and y == 0))
        rho_d = spearman(dp, ds)
        agreement_rows[c]["rho_delta"] = rho_d
        agreement_rows[c]["sign_agree"] = f"{agree}/{len(dp)}"
        print(f"{c:<22}{len(dp):>4}{rho_d:>12.3f}{agree:>8}/{len(dp)}")

    print()
    print("-" * 74)
    print("C. LEAVE-ONE-QUESTION-OUT  (judge-averaged, the registered reading)")
    print("-" * 74)

    def judge_avg(qid, arm, crit):
        return (prim[qid][arm][crit] + sec[qid][arm][crit]) / 2.0

    # H1: wiki - rag on inter_paper_mapping and structural_integrity, n=4
    for crit in ("inter_paper_mapping", "structural_integrity"):
        diffs = {q: judge_avg(q, "wiki_scores", crit) - judge_avg(q, "rag_scores", crit)
                 for q in H1_QIDS}
        full = mean(list(diffs.values()))
        print(f"\n  H1 / {crit}  (threshold +2.0)")
        print(f"    full n=4 mean delta = {full:+.3f}  "
              f"[{'clears' if full >= 2.0 else 'below'}]")
        for q in H1_QIDS:
            loo = mean([v for k, v in diffs.items() if k != q])
            print(f"    drop {q:<34} -> {loo:+.3f}  "
                  f"[{'clears' if loo >= 2.0 else 'below'}]")

    # H2: rag - wiki on groundedness, bias-check tier, n=3
    h2_qids = [q for q in prim if prim[q].get("tier") == H2_TIER]
    diffs = {q: judge_avg(q, "rag_scores", "groundedness") - judge_avg(q, "wiki_scores", "groundedness")
             for q in h2_qids}
    full = mean(list(diffs.values()))
    print(f"\n  H2 / groundedness  (threshold >= 0)")
    print(f"    full n={len(h2_qids)} mean delta = {full:+.3f}  "
          f"[{'meets' if full >= 0 else 'FAILS'}]")
    for q in sorted(diffs):
        loo = mean([v for k, v in diffs.items() if k != q])
        print(f"    drop {q:<34} -> {loo:+.3f}  "
              f"[{'meets' if loo >= 0 else 'FAILS'}]")

    print()
    print("-" * 74)
    print("D. PER-ANSWER LENGTH AND CITATION TELEMETRY")
    print("-" * 74)
    rag = json.loads(RAG_RUN.read_text())
    wiki = json.loads(WIKI_RUN.read_text())
    g = json.loads(GROUNDING.read_text())

    claims = defaultdict(lambda: defaultdict(int))
    cited = defaultdict(lambda: defaultdict(int))
    for row in g["scored"]:
        claims[row["system"]][row["qid"]] += 1
        if row.get("cited_source_idx") not in (None, "", []):
            cited[row["system"]][row["qid"]] += 1

    print(f"{'arm':<10}{'answers':>9}{'out_tok/ans':>13}{'claims/ans':>12}"
          f"{'cited/ans':>11}{'cited%':>9}")
    for name, run, key in (("RAG", rag, "rag"), ("Wiki", wiki, "wiki")):
        res = run["results"]
        out_tok = [r["metadata"].get("completion_tokens", 0)
                   + (r["metadata"].get("thinking_tokens") or 0) for r in res]
        cl = [claims[key][r["id"]] for r in res]
        ci = [cited[key][r["id"]] for r in res]
        tot_cl, tot_ci = sum(cl), sum(ci)
        print(f"{name:<10}{len(res):>9}{mean(out_tok):>13.0f}{mean(cl):>12.1f}"
              f"{mean(ci):>11.1f}{100.0 * tot_ci / tot_cl:>8.1f}%")
    print()
    print("  Reproduction check against published figures: total claims should")
    print("  read RAG 150 / Wiki 316, and claims per answer 11.5 / 24.3.")
    print(f"  computed: RAG {sum(claims['rag'].values())} / "
          f"Wiki {sum(claims['wiki'].values())}")


if __name__ == "__main__":
    main()
