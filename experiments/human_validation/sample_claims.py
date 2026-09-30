#!/usr/bin/env python3
"""Draw the blinded human-validation sample for TMLR #11225.

Joins the claim-level grounding artifact to the two run artifacts, keeps the
cited claims, and draws a tier-stratified sample per system. Emits a blinded
item sheet plus a response form for each annotator, and a separate answer key
holding system, tier and the LLM judge's verdict.

Annotators see the claim and the passages only. Nothing that names the system,
the source file or the judge's verdict reaches the item sheet.

Defaults assume the artifacts of record in experiments/results.
"""

import argparse
import json
import random
import re
from pathlib import Path

# Counts published in Appendix D. Used as a self-check that the right
# artifacts were loaded; a mismatch means a wrong or re-run file.
EXPECTED_CITED = {"rag": 132, "wiki": 241}
EXPECTED_SCORED = 466

VERDICTS = """\
supported   - every factual element of the claim is explicitly stated or
              unambiguously implied by the passages.
partial     - some elements are supported, others go beyond the passages.
contradicted- the passages directly contradict the claim.
unsupported - the claim is not addressed by the passages at all.

Be strict on the supported/partial boundary: any element going beyond the
passages drops the claim to partial."""


def normalize(text):
    """Strip the markup that would tell an annotator which system produced it."""
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load(results_dir, grounding, rag_run, wiki_run):
    g = json.loads((results_dir / grounding).read_text())
    runs = {
        "rag": json.loads((results_dir / rag_run).read_text()),
        "wiki": json.loads((results_dir / wiki_run).read_text()),
    }
    tier, sources = {}, {}
    for system, run in runs.items():
        for r in run["results"]:
            tier[(r["id"], system)] = r["tier"]
            sources[(r["id"], system)] = r["sources"]
    return g, tier, sources


def build_items(g, tier, sources):
    """Cited claims joined to their passages, reproducing the scorer's view.

    The atomizer emitted at least one source index past the end of the source
    list (B2-he-tyka-equilibration-ratios, rag). The scorer dropped those
    silently, so n_cited_chunks counts valid indices only. Dropping them here
    too keeps the annotator's evidence identical to the judge's.
    """
    items = []
    for r in g["scored"]:
        if not r["cited_source_idx"]:
            continue
        key = (r["qid"], r["system"])
        srcs = sources[key]
        valid = [i for i in r["cited_source_idx"] if 0 <= i < len(srcs)]
        assert len(valid) == r["n_cited_chunks"], f"chunk count drift at {key}"

        # Distinct passages, in cited order. A wiki answer can cite two source
        # slots holding byte-identical excerpts of the same page, which the
        # judge saw concatenated. Showing the same text twice tells an
        # annotator nothing, costs reading time, and is a wiki-only tell that
        # would leak the system. The evidence content is unchanged.
        seen, passages = set(), []
        for i in valid:
            text = normalize(srcs[i]["chunk_text"])
            if text not in seen:
                seen.add(text)
                passages.append(text)

        items.append(
            {
                "qid": r["qid"],
                "system": r["system"],
                "tier": tier[key],
                "claim_idx": r["claim_idx"],
                "claim": r["claim"].strip(),
                "passages": passages,
                "n_cited": len(valid),
                "judge_verdict": r["verdict"],
                "judge_reason": r["reason"],
                "dropped_idx": [i for i in r["cited_source_idx"] if i not in valid],
            }
        )
    return items


def allocate(counts, total):
    """Largest-remainder allocation of `total` across strata by size."""
    pool = sum(counts.values())
    exact = {k: v * total / pool for k, v in counts.items()}
    alloc = {k: int(v) for k, v in exact.items()}
    short = total - sum(alloc.values())
    order = sorted(counts, key=lambda k: (-(exact[k] - alloc[k]), k))
    for k in order[:short]:
        alloc[k] += 1
    return alloc


def draw(items, n_per_system, n_calibration, seed):
    """Stratified draw per system, then a calibration set from what is left."""
    rng = random.Random(seed)
    by_system = {}
    for it in items:
        by_system.setdefault(it["system"], {}).setdefault(it["tier"], []).append(it)

    sample, remainder = [], []
    alloc_report = {}
    for system in sorted(by_system):
        strata = by_system[system]
        counts = {t: len(v) for t, v in strata.items()}
        alloc = allocate(counts, n_per_system)
        alloc_report[system] = (counts, alloc)
        for t in sorted(strata):
            pool = sorted(strata[t], key=lambda i: (i["qid"], i["claim_idx"]))
            rng.shuffle(pool)
            sample.extend(pool[: alloc[t]])
            remainder.extend(pool[alloc[t] :])

    rng.shuffle(sample)
    for n, it in enumerate(sample, 1):
        it["item_id"] = f"I{n:03d}"

    rng.shuffle(remainder)
    calibration = remainder[:n_calibration]
    for n, it in enumerate(calibration, 1):
        it["item_id"] = f"C{n:03d}"
    return sample, calibration, alloc_report


def write_sheet(path, items, title):
    lines = [f"# {title}", ""]
    lines += [
        "For each item, read the CLAIM, then the PASSAGES the answer cited for",
        "it, and record one verdict on the response form. Judge only whether the",
        "passages support the claim. Do not use outside knowledge, and do not",
        "judge whether the claim is true in the world.",
        "",
        "```",
        VERDICTS,
        "```",
        "",
        f"{len(items)} items.",
        "",
        "---",
        "",
    ]
    for it in items:
        lines.append(f"## {it['item_id']}")
        lines.append("")
        lines.append(f"**Claim.** {it['claim']}")
        lines.append("")
        label = "Passage" if len(it["passages"]) == 1 else "Passages"
        lines.append(f"**{label} cited ({len(it['passages'])}).**")
        lines.append("")
        for n, p in enumerate(it["passages"], 1):
            if len(it["passages"]) > 1:
                lines.append(f"*({n} of {len(it['passages'])})*")
                lines.append("")
            lines.append("> " + p.replace("\n", "\n> "))
            lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines))


def write_form(path, items):
    rows = ["item_id,verdict,notes"]
    rows += [f"{it['item_id']},," for it in items]
    path.write_text("\n".join(rows) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", type=Path,
                    default=Path(__file__).resolve().parent.parent / "results")
    ap.add_argument("--grounding", default="post-hoc/grounding-20260508T155234Z.json")
    ap.add_argument("--rag-run", default="run-20260506T221602Z.json")
    ap.add_argument("--wiki-run", default="wiki-run-20260506T205500Z.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n-per-system", type=int, default=50)
    ap.add_argument("--calibration", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260919)
    args = ap.parse_args()

    g, tier, sources = load(args.results_dir, args.grounding,
                            args.rag_run, args.wiki_run)
    items = build_items(g, tier, sources)

    cited = {}
    for it in items:
        cited[it["system"]] = cited.get(it["system"], 0) + 1
    print(f"scored claims: {len(g['scored'])} (expected {EXPECTED_SCORED})")
    print(f"cited claims:  {len(items)}  {cited}")
    if len(g["scored"]) != EXPECTED_SCORED or cited != EXPECTED_CITED:
        raise SystemExit("ABORT: counts do not match Appendix D; wrong artifacts?")

    deduped = [it for it in items if len(it["passages"]) != it["n_cited"]]
    if deduped:
        by_system = {}
        for it in deduped:
            by_system[it["system"]] = by_system.get(it["system"], 0) + 1
        print(f"\nclaims citing byte-identical passages twice: {len(deduped)}"
              f"  {by_system}")
        print("  (shown once each; same evidence, and duplicates are a"
              " system tell)")

    dropped = [it for it in items if it["dropped_idx"]]
    if dropped:
        print(f"\nclaims citing a source index past the source list: {len(dropped)}")
        for it in dropped:
            print(f"  {it['qid']} {it['system']} claim {it['claim_idx']}"
                  f" dropped {it['dropped_idx']}")
        print("  (dropped by the scorer too; annotators see the same passages)")

    sample, calibration, alloc_report = draw(
        items, args.n_per_system, args.calibration, args.seed)

    print(f"\nseed {args.seed}")
    for system in sorted(alloc_report):
        counts, alloc = alloc_report[system]
        print(f"\n{system}: {sum(alloc.values())} of {sum(counts.values())} cited")
        for t in sorted(counts):
            print(f"    {t:<16}{alloc[t]:>3} of {counts[t]:>3}")

    n_contra = sum(1 for it in sample if it["judge_verdict"] == "contradicted")
    print(f"\njudge verdicts in the sample:")
    for v in ("supported", "partial", "unsupported", "contradicted"):
        n = sum(1 for it in sample if it["judge_verdict"] == v)
        print(f"    {v:<14}{n:>3}")
    if n_contra == 0:
        print("  note: no contradicted claim was drawn (4 exist in 373)")

    args.out.mkdir(parents=True, exist_ok=True)
    write_sheet(args.out / "items.md", sample,
                "Claim grounding: item sheet")
    write_form(args.out / "response_form.csv", sample)
    write_sheet(args.out / "calibration.md", calibration,
                "Claim grounding: calibration set")
    write_form(args.out / "calibration_form.csv", calibration)

    key = {"seed": args.seed, "grounding": args.grounding,
           "atomizer_model": g["atomizer_model"], "scorer_model": g["scorer_model"],
           "items": sample, "calibration": calibration}
    (args.out / "answer_key.json").write_text(json.dumps(key, indent=2))

    print(f"\nwrote {args.out}/")
    print("    items.md, response_form.csv         <- to each annotator")
    print("    calibration.md, calibration_form.csv <- calibration round")
    print("    answer_key.json                      <- KEEP BACK")


if __name__ == "__main__":
    main()
