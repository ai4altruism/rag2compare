#!/usr/bin/env python3
"""Analyze the human-validation labels for TMLR #11225.

Implements the analyses fixed in human_validation/PRESPECIFICATION.md
before any label existed. Reports, in the pre-specified order:

  P2  human-human agreement, first, because it sets the scale for P1
  P1  judge-human agreement, four-way and on the binary supported cut
  P3  unsupported-rate contrast on human labels
  P4  supported-rate contrast on human labels
      cited-passage length as a covariate, within system
      the two pre-specified decision rules, applied

Reads the answer key plus the returned forms. Drop the filled forms into the
pack directory as response_form_<name>.csv, and an adjudicated consensus, if
one was produced, as consensus.csv.
"""

import argparse
import csv
import json
import math
import re
from pathlib import Path

VERDICTS = ("supported", "partial", "contradicted", "unsupported")

# Cited-claim universe per system, from Appendix D. The sample is drawn from
# these, so the finite-population correction uses them.
UNIVERSE = {"rag": 132, "wiki": 241}

# Pre-specified floors. Below either, the judge is reported as not validated.
MIN_BINARY_AGREEMENT = 0.70
MIN_KAPPA = 0.40


def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def prop_ci(k, n, population=None):
    """Normal-approximation interval, with the finite-population correction.

    Normal approximation because that is what the pre-specification committed
    to and what its +/-7.7 figure was computed from.
    """
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    var = p * (1 - p) / n
    if population and population > 1:
        var *= (population - n) / (population - 1)
    half = 1.96 * math.sqrt(var)
    return p, max(0.0, p - half), min(1.0, p + half)


def two_proportion(k1, n1, N1, k2, n2, N2):
    """Two-sided z test for a difference in proportions, each with an fpc."""
    p1, p2 = k1 / n1, k2 / n2
    v1 = p1 * (1 - p1) / n1 * ((N1 - n1) / (N1 - 1) if N1 > 1 else 1)
    v2 = p2 * (1 - p2) / n2 * ((N2 - n2) / (N2 - 1) if N2 > 1 else 1)
    se = math.sqrt(v1 + v2)
    if se == 0:
        return p1, p2, float("nan"), float("nan")
    z = (p1 - p2) / se
    return p1, p2, z, 2 * (1 - phi(abs(z)))


def agreement(a, b):
    """Raw agreement and Cohen's kappa between two equal-length label lists."""
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    k = (po - pe) / (1 - pe) if pe < 1 else float("nan")
    return po, k, n


def binary(labels):
    return ["supported" if v == "supported" else "not" for v in labels]


def read_form(path):
    out = {}
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            item = (row.get("item_id") or "").strip()
            verdict = (row.get("verdict") or "").strip().lower()
            if not item:
                continue
            if verdict not in VERDICTS:
                raise SystemExit(
                    f"{path.name}: item {item} has verdict {verdict!r};"
                    f" expected one of {', '.join(VERDICTS)}")
            out[item] = verdict
    return out


def load(pack):
    key = json.loads((pack / "answer_key.json").read_text())
    items = {it["item_id"]: it for it in key["items"]}

    forms = {}
    for path in sorted(pack.glob("response_form_*.csv")):
        name = re.sub(r"^response_form_|\.csv$", "", path.name)
        forms[name] = read_form(path)
    consensus_path = pack / "consensus.csv"
    consensus = read_form(consensus_path) if consensus_path.exists() else None

    if len(forms) < 2:
        raise SystemExit(
            f"found {len(forms)} annotator form(s) in {pack}; the design needs"
            " two. Name them response_form_<name>.csv")
    for name, form in forms.items():
        missing = set(items) - set(form)
        if missing:
            raise SystemExit(
                f"{name}: {len(missing)} of {len(items)} items unscored"
                f" (first: {sorted(missing)[0]})")
    return key, items, forms, consensus


def aligned(items, labels):
    ids = sorted(items)
    return ids, [labels[i] for i in ids], [items[i]["judge_verdict"] for i in ids]


def rate_contrast(items, labels, verdict, label):
    """Compare one verdict's rate between the two systems on human labels."""
    counts = {}
    for system in ("rag", "wiki"):
        ids = [i for i in items if items[i]["system"] == system]
        hit = sum(1 for i in ids if labels[i] == verdict)
        counts[system] = (hit, len(ids))
    (kr, nr), (kw, nw) = counts["rag"], counts["wiki"]
    pr, pw, z, p = two_proportion(kr, nr, UNIVERSE["rag"],
                                  kw, nw, UNIVERSE["wiki"])
    print(f"\n  {label}")
    print(f"    rag   {kr:>3}/{nr:<3} = {pr:6.1%}")
    print(f"    wiki  {kw:>3}/{nw:<3} = {pw:6.1%}")
    print(f"    difference {pr - pw:+.1%}   z = {z:.2f}   p = {p:.4f}"
          f"   {'significant' if p < 0.05 else 'NOT significant'} at 0.05")
    return pr, pw, p


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path,
                    default=Path("pack"))
    args = ap.parse_args()

    key, items, forms, consensus = load(args.pack)
    names = sorted(forms)
    n = len(items)

    print(f"pack: {args.pack}")
    print(f"items: {n}   annotators: {', '.join(names)}"
          f"   consensus: {'yes' if consensus else 'no'}")
    print(f"seed {key['seed']}, judge {key['scorer_model']}")

    # ---- P2, first, because it sets the scale for P1 -----------------------
    print("\n" + "=" * 70)
    print("P2. HUMAN-HUMAN AGREEMENT (reported first: it scales P1)")
    print("=" * 70)
    ids = sorted(items)
    a, b = [forms[names[0]][i] for i in ids], [forms[names[1]][i] for i in ids]
    po4, k4, _ = agreement(a, b)
    pob, kb, _ = agreement(binary(a), binary(b))
    _, lo, hi = prop_ci(round(pob * n), n, sum(UNIVERSE.values()))
    print(f"  four-way   raw {po4:.1%}   kappa {k4:.3f}")
    print(f"  binary     raw {pob:.1%}   kappa {kb:.3f}"
          f"   95% CI [{lo:.1%}, {hi:.1%}]")
    print("\n  Read P1 against this. A judge sitting near the center of human"
          "\n  disagreement can exceed it, which is not evidence that it beats"
          "\n  a human.")
    if pob < 0.70:
        print("  WARNING: the annotators agree weakly, so a low P1 indicates"
              " an ambiguous task rather than a failing judge.")

    # ---- P1 ----------------------------------------------------------------
    print("\n" + "=" * 70)
    print("P1. JUDGE-HUMAN AGREEMENT")
    print("=" * 70)
    raters = [(nm, forms[nm]) for nm in names]
    if consensus:
        raters.append(("consensus", consensus))
    for label, labels in raters:
        _, human, judge = aligned(items, labels)
        po4, k4, _ = agreement(human, judge)
        pob, kb, _ = agreement(binary(human), binary(judge))
        _, lo, hi = prop_ci(round(pob * n), n, sum(UNIVERSE.values()))
        print(f"\n  judge vs {label}")
        print(f"    four-way   raw {po4:.1%}   kappa {k4:.3f}")
        print(f"    binary     raw {pob:.1%}   kappa {kb:.3f}"
              f"   95% CI [{lo:.1%}, {hi:.1%}]")

    # Everything downstream runs on the adjudicated consensus when there is
    # one, and on the first annotator otherwise.
    src = consensus if consensus else forms[names[0]]
    rule_label = "consensus" if consensus else names[0]
    _, human, judge = aligned(items, src)
    rule_binary, rule_kappa, _ = agreement(binary(human), binary(judge))

    # ---- P3 and P4 ---------------------------------------------------------
    print("\n" + "=" * 70)
    print("P3 / P4. RATE CONTRASTS ON HUMAN LABELS")
    print("=" * 70)
    print(f"  labels: {rule_label}"
          + ("" if consensus else "  (no consensus file; first annotator used)"))
    print(f"  judge's own rates, for reference:"
          f" unsupported rag 34.1% / wiki 6.2%;"
          f" supported rag 18.9% / wiki 40.2%")
    _, _, p3 = rate_contrast(items, src, "unsupported",
                             "P3. unsupported rate (judge gap was 4-5x)")
    _, _, p4 = rate_contrast(items, src, "supported",
                             "P4. supported rate (judge gap was ~2x)")

    # ---- covariate ---------------------------------------------------------
    print("\n" + "=" * 70)
    print("COVARIATE. CITED-PASSAGE LENGTH, WITHIN SYSTEM")
    print("=" * 70)
    print("  Pre-committed because rag cites 5.9x more evidence per claim.")
    for system in ("rag", "wiki"):
        ids_s = [i for i in items if items[i]["system"] == system]
        lens = {i: sum(len(p.split()) for p in items[i]["passages"])
                for i in ids_s}
        med = sorted(lens.values())[len(ids_s) // 2]
        print(f"\n  {system} (median {med} words)")
        for half, keep in (("shorter", lambda v: v <= med),
                           ("longer", lambda v: v > med)):
            sub = [i for i in ids_s if keep(lens[i])]
            if not sub:
                continue
            sup = sum(1 for i in sub if src[i] == "supported")
            uns = sum(1 for i in sub if src[i] == "unsupported")
            print(f"    {half:<8} n={len(sub):<3}"
                  f" supported {sup / len(sub):6.1%}"
                  f"  unsupported {uns / len(sub):6.1%}")

    # ---- decision rules ----------------------------------------------------
    print("\n" + "=" * 70)
    print("PRE-SPECIFIED DECISION RULES")
    print("=" * 70)
    ok = rule_binary >= MIN_BINARY_AGREEMENT and rule_kappa >= MIN_KAPPA
    print(f"  binary judge-human agreement {rule_binary:.1%}"
          f"  (floor {MIN_BINARY_AGREEMENT:.0%})")
    print(f"  binary kappa {rule_kappa:.3f}"
          f"  (floor {MIN_KAPPA:.2f})")
    print(f"\n  -> the judge is {'VALIDATED' if ok else 'NOT validated'}"
          " on the pre-specified rule")
    if not ok:
        print("     Report the claim-level rates as LLM-scored without human"
              " corroboration, and narrow them rather than defend them.")
    if p3 >= 0.05:
        print("  -> P3 did not reach significance: the strongest claim-level"
              " result does not survive human scoring. Section 5.4 must say so.")
    if p4 >= 0.05:
        print("  -> P4 did not reach significance: narrow the 'about twice as"
              " often supported' sentence to the judged labels. At ~80% power"
              " this is weak evidence of absence, and reports as such.")


if __name__ == "__main__":
    main()
