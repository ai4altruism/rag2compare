"""Run the full preregistered analysis end-to-end.

Reproduces every number reported in findings-2026-05-06.md from the five
run artifacts:

    experiments/results/ingest-20260506T202904Z.json
    experiments/results/run-20260506T221602Z.json
    experiments/results/wiki-ingest-20260506T211731Z.json
    experiments/results/wiki-run-20260506T205500Z.json
    experiments/results/judged-20260506T225645Z.json

The Bayesian model in §6.2 follows the OSF preregistration verbatim:
score_diff ~ Normal(mu, sigma); mu ~ Normal(0, 4); sigma ~ HalfNormal(4),
fit per criterion x tier with NUTS (4 chains x 2000 iter x 2000 warmup).

Run:
    python -m venv venv && . venv/bin/activate
    pip install pymc numpy
    PYTENSOR_FLAGS="cxx=" python experiments/run_preregistered_analysis.py
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pymc as pm
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"

JUDGED = RESULTS / "judged-20260506T225645Z.json"
RAG_INGEST = RESULTS / "ingest-20260506T202904Z.json"
RAG_RUN = RESULTS / "run-20260506T221602Z.json"
WIKI_INGEST = RESULTS / "wiki-ingest-20260506T211731Z.json"
WIKI_RUN = RESULTS / "wiki-run-20260506T205500Z.json"

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
PREREG_IRR_QIDS = [
    "B1-devote3-confidence-interval",
    "T3-mia-as-copyright-evidence",
    "T1-cardio-baselines",
]
CRITS = ["groundedness", "structural_integrity", "conflict_awareness", "inter_paper_mapping"]


def load():
    with open(JUDGED) as f:
        j = json.load(f)
    primary = {x["question_id"]: x for x in j["judgments"]}
    secondary = {x["question_id"]: x for x in j["secondary"]["judgments"]}
    with open(RAG_INGEST) as f:
        rag_ingest = json.load(f)
    with open(RAG_RUN) as f:
        rag_run = json.load(f)
    with open(WIKI_INGEST) as f:
        wiki_ingest = json.load(f)
    with open(WIKI_RUN) as f:
        wiki_run = json.load(f)
    return primary, secondary, rag_ingest, rag_run, wiki_ingest, wiki_run


def per_q_diff(primary, secondary, qids, crit, sign="wiki-rag"):
    out = []
    for q in qids:
        if sign == "wiki-rag":
            p = primary[q]["wiki_scores"][crit] - primary[q]["rag_scores"][crit]
            s = secondary[q]["wiki_scores"][crit] - secondary[q]["rag_scores"][crit]
        else:
            p = primary[q]["rag_scores"][crit] - primary[q]["wiki_scores"][crit]
            s = secondary[q]["rag_scores"][crit] - secondary[q]["wiki_scores"][crit]
        out.append((p, s, (p + s) / 2))
    return out


def fit_bayes(diffs, threshold, label):
    """Preregistered model: score_diff ~ Normal(mu, sigma);
    mu ~ Normal(0, 4); sigma ~ HalfNormal(4)."""
    with pm.Model():
        mu = pm.Normal("mu", mu=0, sigma=4)
        sigma = pm.HalfNormal("sigma", sigma=4)
        pm.Normal("obs", mu=mu, sigma=sigma, observed=np.array(diffs))
        idata = pm.sample(
            2000, tune=2000, chains=4, target_accept=0.95,
            random_seed=42, progressbar=False, return_inferencedata=True,
            compute_convergence_checks=False,
        )
    mu_post = idata.posterior["mu"].values.flatten()
    rhat = pm.rhat(idata)
    ess = pm.ess(idata)
    return {
        "label": label,
        "n": len(diffs),
        "data": list(diffs),
        "mean": float(mu_post.mean()),
        "sd": float(mu_post.std()),
        "ci95": [float(np.percentile(mu_post, 2.5)), float(np.percentile(mu_post, 97.5))],
        "P_ge_threshold": float((mu_post >= threshold).mean()),
        "P_ge_zero": float((mu_post >= 0).mean()),
        "rhat_mu": float(rhat.mu.values),
        "rhat_sigma": float(rhat.sigma.values),
        "ess_mu": float(ess.mu.values),
        "ess_sigma": float(ess.sigma.values),
    }


def bootstrap_ci(data, n=10000, ci=0.95, seed=42):
    rng = np.random.default_rng(seed)
    arr = np.array(data)
    means = np.array([rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n)])
    lo, hi = np.percentile(means, [(1 - ci) / 2 * 100, (1 + ci) / 2 * 100])
    return float(arr.mean()), float(lo), float(hi)


def main():
    primary, secondary, rag_ingest, rag_run, wiki_ingest, wiki_run = load()

    # --- Manipulation check (prereg §Other planned analyses, point 0)
    print("=" * 76)
    print("MANIPULATION CHECK")
    for label, run in [("RAG", rag_run), ("Wiki", wiki_run)]:
        models = Counter(r["metadata"].get("model_used") for r in run["results"])
        efforts = Counter(r["metadata"].get("reasoning_effort") for r in run["results"])
        print(f"  {label}: model={dict(models)} effort={dict(efforts)}")

    # --- H1 confirmatory
    print("\n" + "=" * 76)
    print("H1 — Wiki - RAG >= +2.0 on inter_paper_mapping AND structural_integrity")
    print("     (multi-hop + emergence tier, n=4)")
    h1 = {}
    for crit in ["structural_integrity", "inter_paper_mapping"]:
        diffs = per_q_diff(primary, secondary, H1_QIDS, crit, "wiki-rag")
        p = [d[0] for d in diffs]
        avg = [d[2] for d in diffs]
        h1[crit] = {"primary": p, "judge_avg": avg}
        print(f"\n  {crit}:")
        print(f"    primary diffs: {p} -> mean {np.mean(p):+.3f}")
        print(f"    judge-avg:     {avg} -> mean {np.mean(avg):+.3f}")

    # --- H2 confirmatory
    print("\n" + "=" * 76)
    print("H2 — RAG - Wiki >= 0 on groundedness for bias-check (n=3)")
    diffs = per_q_diff(primary, secondary, H2_QIDS, "groundedness", "rag-wiki")
    h2_p = [d[0] for d in diffs]
    h2_avg = [d[2] for d in diffs]
    print(f"  primary RAG-Wiki: {h2_p} -> mean {np.mean(h2_p):+.3f}")
    print(f"  judge-avg:        {h2_avg} -> mean {np.mean(h2_avg):+.3f}")

    # --- H3 confirmatory
    print("\n" + "=" * 76)
    print("H3 — H3a (wiki ingest > rag ingest) AND H3b (rag query > wiki query)")
    T_ingest_rag = sum(d["prompt_tokens"] + d["completion_tokens"] for d in rag_ingest["documents"])
    T_ingest_wiki = wiki_ingest["totals"]["tokens_in"] + wiki_ingest["totals"]["tokens_out"]
    T_query_rag = sum(
        r["metadata"]["prompt_tokens"] + r["metadata"]["completion_tokens"] + r["metadata"]["thinking_tokens"]
        for r in rag_run["results"]
    )
    T_query_wiki = sum(
        r["metadata"]["prompt_tokens"] + r["metadata"]["completion_tokens"] + r["metadata"]["thinking_tokens"]
        for r in wiki_run["results"]
    )
    print(f"  T_ingest[rag]  = {T_ingest_rag:,}")
    print(f"  T_ingest[wiki] = {T_ingest_wiki:,}")
    print(f"  T_query[rag]   = {T_query_rag:,}")
    print(f"  T_query[wiki]  = {T_query_wiki:,}")
    h3a = T_ingest_wiki > T_ingest_rag
    h3b = T_query_rag > T_query_wiki
    print(f"  H3a supported: {h3a}")
    print(f"  H3b supported: {h3b}  (refuted; opposite direction)")
    denom = T_query_rag / 13 - T_query_wiki / 13
    if denom != 0:
        n_cross = (T_ingest_wiki - T_ingest_rag) / denom
        print(f"  N_crossover_queries = {n_cross:,.0f} (negative -> no crossover)")

    # --- IRR
    print("\n" + "=" * 76)
    print("IRR (max-delta over question x system)")
    print("\n  Full coverage (n=13, expansion of preregistered n=3):")
    for c in CRITS:
        deltas = []
        for q in primary:
            for s in ["rag", "wiki"]:
                deltas.append(abs(primary[q][f"{s}_scores"][c] - secondary[q][f"{s}_scores"][c]))
        md = max(deltas)
        flag = " [> 2 -> adjustment fires]" if md > 2 else ""
        print(f"    {c}: {md}{flag}")
    print(f"\n  Preregistered n=3 ({PREREG_IRR_QIDS}):")
    for c in CRITS:
        deltas = []
        for q in PREREG_IRR_QIDS:
            for s in ["rag", "wiki"]:
                deltas.append(abs(primary[q][f"{s}_scores"][c] - secondary[q][f"{s}_scores"][c]))
        md = max(deltas)
        flag = " [> 2 -> adjustment fires]" if md > 2 else ""
        print(f"    {c}: {md}{flag}")

    # --- Bootstrap CI (preregistered robustness check 1)
    print("\n" + "=" * 76)
    print("ROBUSTNESS 1: BOOTSTRAP 95% CI (10,000 resamples)")
    for crit in ["structural_integrity", "inter_paper_mapping"]:
        m, lo, hi = bootstrap_ci(h1[crit]["judge_avg"])
        excl = "excludes" if lo >= 2.0 else "includes"
        print(f"  H1 {crit} (judge-avg): mean={m:+.3f} CI=[{lo:+.3f},{hi:+.3f}]  ({excl} +2.0)")
        m, lo, hi = bootstrap_ci(h1[crit]["primary"])
        excl = "excludes" if lo >= 2.0 else "includes"
        print(f"  H1 {crit} (primary):   mean={m:+.3f} CI=[{lo:+.3f},{hi:+.3f}]  ({excl} +2.0)")
    m, lo, hi = bootstrap_ci(h2_avg)
    excl = "excludes" if lo >= 0 else "includes"
    print(f"  H2 groundedness (judge-avg): mean={m:+.3f} CI=[{lo:+.3f},{hi:+.3f}]  ({excl} 0)")
    m, lo, hi = bootstrap_ci(h2_p)
    excl = "excludes" if lo >= 0 else "includes"
    print(f"  H2 groundedness (primary):   mean={m:+.3f} CI=[{lo:+.3f},{hi:+.3f}]  ({excl} 0)")

    # --- Bayesian (preregistered robustness check 2)
    print("\n" + "=" * 76)
    print("ROBUSTNESS 2: BAYESIAN MODEL (preregistered)")
    print("score_diff ~ Normal(mu, sigma); mu ~ Normal(0, 4); sigma ~ HalfNormal(4)")
    print("NUTS: 4 chains x 2000 iter x 2000 warmup")
    bayes = []
    for crit in ["structural_integrity", "inter_paper_mapping"]:
        bayes.append(fit_bayes(h1[crit]["judge_avg"], 2.0, f"H1:{crit}:judge-avg"))
        bayes.append(fit_bayes(h1[crit]["primary"], 2.0, f"H1:{crit}:primary"))
    bayes.append(fit_bayes(h2_avg, 0.0, "H2:groundedness:judge-avg"))
    bayes.append(fit_bayes(h2_p, 0.0, "H2:groundedness:primary"))
    print()
    for r in bayes:
        thresh = 2.0 if r["label"].startswith("H1") else 0.0
        p_key = "P_ge_threshold" if thresh > 0 else "P_ge_zero"
        strong = " STRONG" if r[p_key] >= 0.95 else ""
        print(
            f"  {r['label']}: mean={r['mean']:+.3f} sd={r['sd']:.3f} "
            f"CI95=[{r['ci95'][0]:+.3f},{r['ci95'][1]:+.3f}] "
            f"P(mu>={thresh:.0f})={r[p_key]:.4f}{strong} "
            f"R̂={r['rhat_mu']:.3f} ESS={r['ess_mu']:.0f}"
        )

    # --- Other planned analyses
    print("\n" + "=" * 76)
    print("BIAS-TAG STRATIFICATION (manipulation-design check)")
    by_bias = defaultdict(lambda: defaultdict(list))
    for q, p in primary.items():
        for c in CRITS:
            by_bias[p["bias"]][f"{c}:rag"].append(p["rag_scores"][c])
            by_bias[p["bias"]][f"{c}:wiki"].append(p["wiki_scores"][c])
    for bias in ["rag", "wiki", "neutral"]:
        n = len(by_bias[bias][CRITS[0] + ":rag"])
        line = f"  bias={bias} n={n}: "
        for c in CRITS:
            r = np.mean(by_bias[bias][f"{c}:rag"])
            w = np.mean(by_bias[bias][f"{c}:wiki"])
            line += f"{c[:8]}({r:.2f}/{w:.2f}/{w-r:+.2f}) "
        print(line)

    print("\n" + "=" * 76)
    print("LATENCY")
    rag_lat = [r["metadata"]["latency_ms"] for r in rag_run["results"]]
    wiki_lat = [r["metadata"]["latency_ms"] for r in wiki_run["results"]]
    print(f"  RAG  total {sum(rag_lat)/60000:.1f}min mean {np.mean(rag_lat)/1000:.1f}s")
    print(f"  Wiki total {sum(wiki_lat)/60000:.1f}min mean {np.mean(wiki_lat)/1000:.1f}s")
    print(f"  Ratio (wiki/rag): {sum(wiki_lat)/sum(rag_lat):.2f}x")

    print("\n" + "=" * 76)
    print("ADAPTIVE-THINKING ENGAGEMENT")
    for label, run in [("RAG", rag_run), ("Wiki", wiki_run)]:
        nz = sum(1 for r in run["results"] if r["metadata"]["thinking_tokens"] > 0)
        print(f"  {label}: thinking_tokens > 0 on {nz}/13 questions")


if __name__ == "__main__":
    main()
