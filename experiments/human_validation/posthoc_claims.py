#!/usr/bin/env python3
"""Post-hoc breakdown of the human-validation labels for TMLR #11225.

Everything here is exploratory and outside the pre-specification. The
pre-specified analyses are in analyze_claims.py, and this script leaves
them untouched. It exists because on 2026-09-26 the original claim-level
scorer was found to cut every cited passage to 1,500 characters
(run_claim_grounding.truncate), while the annotators read full passages.

  --forms   imports returned forms (.csv or .xlsx) into the pack as the
            verdict-only response_form_<name>.csv files the analysis reads;
            notes are not carried, because the analysis never reads them
  then      judge-human agreement by system and by cap exposure, the
            confusion matrices, both rate contrasts on each annotator, the
            range any adjudicated consensus can reach, and a term-location
            check on the items the judge called unsupported and both
            annotators called supported

  --rescore  compares a rescore from rag2compare's
            experiments/rescore_claim_grounding.py with the annotators and
            with the original judge; --control adds the capped rerun of the
            original requests, which measures rerun noise alone

    python3 experiments/human_validation/posthoc_claims.py --pack <pack> \\
        --forms raw/response_form_1.csv raw/response_form_2.xlsx
    python3 experiments/human_validation/posthoc_claims.py --pack <pack> \\
        --rescore <rescore-main-capnone-*.json> \\
        --control <rescore-main-cap1500-rag-*.json>
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_claims import (UNIVERSE, VERDICTS, agreement, binary,  # noqa: E402
                                two_proportion)

ORIGINAL_CAP = 1500
SYSTEMS = ("rag", "wiki")
XNS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
STOP = {"passage", "passages", "paper", "which", "their", "about", "there",
        "these", "those", "because", "between", "through"}


def read_xlsx(path):
    """First sheet, columns A and B, with the standard library only."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(XNS + "t"))
                  for si in root.findall(XNS + "si")]
    out = {}
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    for row in sheet.iter(XNS + "row"):
        cells = {}
        for c in row.findall(XNS + "c"):
            v = c.find(XNS + "v")
            if v is None:
                continue
            col = re.match(r"[A-Z]+", c.get("r")).group()
            cells[col] = shared[int(v.text)] if c.get("t") == "s" else v.text
        item = (cells.get("A") or "").strip()
        if re.fullmatch(r"I\d+", item):
            out[item] = (cells.get("B") or "").strip().lower()
    return out


def read_csv(path):
    with path.open(newline="") as fh:
        return {r["item_id"].strip(): (r.get("verdict") or "").strip().lower()
                for r in csv.DictReader(fh) if (r.get("item_id") or "").strip()}


def import_forms(pack, paths):
    for path in paths:
        name = re.sub(r"^response_form_", "", path.stem)
        labels = read_xlsx(path) if path.suffix == ".xlsx" else read_csv(path)
        bad = {i: v for i, v in labels.items() if v not in VERDICTS}
        if bad:
            raise SystemExit(f"{path.name}: out-of-vocabulary verdicts {bad}")
        dest = pack / f"response_form_{name}.csv"
        with dest.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["item_id", "verdict", "notes"])
            for item in sorted(labels):
                w.writerow([item, labels[item], ""])
        print(f"imported {path} -> {dest.name} ({len(labels)} items)")


def rescore_rows(path):
    """{(system, qid, claim_idx): row} from a rescore output file."""
    data = json.loads(path.read_text())
    if data.get("kind") != "claim-grounding-rescore":
        raise SystemExit(f"{path.name}: not a claim-grounding rescore")
    return data, {(r["system"], r["qid"], r["claim_idx"]): r
                  for r in data["rows"]}


def report_rescore(items, forms, names, path, control_path):
    data, rows = rescore_rows(path)
    print("\n" + "=" * 70)
    print(f"RESCORED JUDGE: {path.name}")
    print(f"  cap {data['cap']}, scorer {data['scorer_model']},"
          f" served {', '.join(data['served_models'])}")
    print("=" * 70)
    new = {}
    for i, it in items.items():
        k = (it["system"], it["qid"], it["claim_idx"])
        if k not in rows:
            raise SystemExit(f"{i}: {k} missing from {path.name}")
        if rows[k]["original_verdict"] != it["judge_verdict"]:
            raise SystemExit(f"{i}: original verdict disagrees with the key")
        new[i] = rows[k]["verdict"]
    old = {i: it["judge_verdict"] for i, it in items.items()}
    ids = sorted(items)
    for label, judge in (("original judge", old), ("rescored judge", new)):
        print(f"\n  {label}")
        for n in names:
            human = [forms[n][i] for i in ids]
            j = [judge[i] for i in ids]
            po4, k4, _ = agreement(human, j)
            pob, kb, _ = agreement(binary(human), binary(j))
            per = "   ".join(
                f"{s} {sum(binary([judge[i]]) == binary([forms[n][i]]) for i in ids if items[i]['system'] == s)}/50"
                for s in SYSTEMS)
            print(f"    vs {n}: four-way {po4:.1%} (kappa {k4:.3f})"
                  f"   binary {pob:.1%} (kappa {kb:.3f})   {per}")
    print("\n  pre-specified floors, applied post-hoc to the rescored judge:"
          " binary 70%, kappa 0.40")

    print("\n  sample verdicts moved by the rescore:",
          dict(sorted(Counter(f"{old[i]}->{new[i]}" for i in ids
                              if old[i] != new[i]).items())))

    print("\n  all cited claims, original -> rescored")
    for s in SYSTEMS:
        cited = [r for r in rows.values()
                 if r["system"] == s and r["n_cited_chunks"] > 0]
        n = len(cited)
        for v in ("supported", "unsupported"):
            a = sum(r["original_verdict"] == v for r in cited)
            b = sum(r["verdict"] == v for r in cited)
            print(f"    {s:<5} {v:<12} {a / n:6.1%} -> {b / n:6.1%}  (n={n})")
        flips = sum(r["verdict"] != r["original_verdict"] for r in cited)
        print(f"    {s:<5} verdicts changed {flips}/{n}")

    if control_path:
        cdata, crows = rescore_rows(control_path)
        print(f"\n  rerun-noise control: {control_path.name}"
              f" (cap {cdata['cap']}, systems {', '.join(cdata['systems'])})")
        keys = [k for k, r in crows.items() if r["n_cited_chunks"] > 0]
        flips = sum(crows[k]["verdict"] != crows[k]["original_verdict"]
                    for k in keys)
        print(f"    identical requests rerun: {flips}/{len(keys)} verdicts"
              " changed, which is noise alone")
        moved = sum(rows[k]["verdict"] != rows[k]["original_verdict"]
                    for k in keys)
        print(f"    same claims with the cap removed: {moved}/{len(keys)}"
              " changed, which is noise plus the cap")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pack", type=Path,
                    default=Path("pack"))
    ap.add_argument("--forms", type=Path, nargs="*", default=[])
    ap.add_argument("--rescore", type=Path)
    ap.add_argument("--control", type=Path)
    args = ap.parse_args()

    if args.forms:
        import_forms(args.pack, args.forms)
    key = json.loads((args.pack / "answer_key.json").read_text())
    items = {it["item_id"]: it for it in key["items"]}
    forms = {re.sub(r"^response_form_", "", p.stem): read_csv(p)
             for p in sorted(args.pack.glob("response_form_*.csv"))}
    names = sorted(forms)
    if len(names) != 2:
        raise SystemExit(f"expected two annotator forms, found {names}")
    a1, a2 = forms[names[0]], forms[names[1]]
    judge = {i: it["judge_verdict"] for i, it in items.items()}
    cut = {i: any(len(p) > ORIGINAL_CAP for p in it["passages"])
           for i, it in items.items()}
    by_sys = {s: sorted(i for i in items if items[i]["system"] == s)
              for s in SYSTEMS}

    def bin_agree(ids, x, y):
        return sum(binary([x[i]]) == binary([y[i]]) for i in ids)

    print("POST-HOC, NOT PRE-SPECIFIED")
    print(f"annotators: {', '.join(names)}   items: {len(items)}")

    print("\nPassages over the original 1,500-character cap, by system")
    for s in SYSTEMS:
        print(f"  {s:<5} {sum(cut[i] for i in by_sys[s])} of {len(by_sys[s])}")

    print("\nBinary agreement by system")
    for s in SYSTEMS:
        ids = by_sys[s]
        parts = [f"judge vs {n} {bin_agree(ids, judge, forms[n])}/{len(ids)}"
                 for n in names]
        parts.append(f"{names[0]} vs {names[1]}"
                     f" {bin_agree(ids, a1, a2)}/{len(ids)}")
        print(f"  {s:<5} " + "   ".join(parts))

    print("\nConfusion, judge rows by annotator columns")
    for n in names:
        for s in SYSTEMS:
            print(f"\n  annotator {n}, {s}"
                  + "".join(f"{v[:6]:>8}" for v in VERDICTS))
            for jv in VERDICTS:
                row = [sum(1 for i in by_sys[s]
                           if judge[i] == jv and forms[n][i] == hv)
                       for hv in VERDICTS]
                if sum(row):
                    print(f"    {jv:<14}" + "".join(f"{x:>8}" for x in row))

    print("\nRate contrasts on each annotator (the analysis script uses the"
          " first only)")
    for verdict in ("unsupported", "supported"):
        for n in names:
            k = {s: sum(forms[n][i] == verdict for i in by_sys[s])
                 for s in SYSTEMS}
            _, _, z, p = two_proportion(k["rag"], 50, UNIVERSE["rag"],
                                        k["wiki"], 50, UNIVERSE["wiki"])
            print(f"  {verdict:<12} annotator {n}: rag {k['rag']}/50"
                  f"  wiki {k['wiki']}/50   z = {z:.2f}  p = {p:.4f}")

    print("\nWhat any adjudicated consensus can reach")
    ids = sorted(items)
    best = sum(1 for i in ids if binary([judge[i]]) in
               (binary([a1[i]]), binary([a2[i]])))
    worst = sum(1 for i in ids if binary([judge[i]]) == binary([a1[i]])
                == binary([a2[i]]))
    print(f"  binary judge-consensus agreement between {worst} and {best}"
          f" of {len(ids)}; the pre-specified floor is 70")
    rng = {s: (sum(1 for i in by_sys[s] if a1[i] == a2[i] == "unsupported"),
               sum(1 for i in by_sys[s] if "unsupported" in (a1[i], a2[i])))
           for s in SYSTEMS}
    for kr in range(rng["rag"][0], rng["rag"][1] + 1):
        for kw in range(rng["wiki"][0], rng["wiki"][1] + 1):
            _, _, z, p = two_proportion(kr, 50, UNIVERSE["rag"],
                                        kw, 50, UNIVERSE["wiki"])
            print(f"  P3 with consensus unsupported rag {kr}/50,"
                  f" wiki {kw}/50: z = {z:.2f}  p = {p:.4f}")

    print("\nJudge unsupported, both annotators supported: where do the"
          " claim's terms sit?")
    print("  (a term check, not a reading: tokens of six or more letters"
          " and numbers)")
    rows = [i for i in ids if judge[i] == "unsupported"
            and a1[i] == a2[i] == "supported"]
    for i in rows:
        it = items[i]
        toks = {t for t in re.findall(r"[A-Za-z][A-Za-z\-]{5,}|\d[\d.,%]*\d|\d",
                                      it["claim"]) if t.lower() not in STOP}
        low = [p.lower() for p in it["passages"]]
        early = sum(1 for t in toks if any(t.lower() in p[:ORIGINAL_CAP]
                                           for p in low))
        late = sum(1 for t in toks
                   if not any(t.lower() in p[:ORIGINAL_CAP] for p in low)
                   and any(t.lower() in p[ORIGINAL_CAP:] for p in low))
        print(f"  {i} {it['system']:<4} longest {max(map(len, it['passages'])):>5}"
              f"  terms {len(toks):>2}  before cap {early:>2}"
              f"  only after cap {late:>2}")
    print(f"  {len(rows)} items; {sum(1 for i in rows if cut[i])} had a"
          " passage over the cap")

    if args.rescore:
        report_rescore(items, forms, names, args.rescore, args.control)


if __name__ == "__main__":
    main()
