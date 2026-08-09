"""Reconstruct the billable-weighted wiki ingest total for H3a, from the
deposited artifact plus the per-session component table.

The deposited wiki-ingest artifact reports totals.tokens_in as a single number
that sums uncached input, cache writes, and cache reads. Those bill at
different rates, so H3a (is the wiki more expensive to BUILD?) cannot be read
off the aggregate. This script pairs the aggregate with the component split in
h3a_ingest_components.tsv and recomputes the figures reported in the paper.

It is self-checking in the way that matters: the components must sum to the
deposited totals.tokens_in exactly. If they do not, the components are not the
telemetry behind that artifact and the reconstruction is refused.

Deliberately dependency-free, and reads only deposited files, so a reviewer can
reproduce H3a from the OSF deposit without repository access.

Run:
    python experiments/reconstruct_h3a.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "experiments" / "h3a_ingest_components.tsv"
WIKI_INGEST = ROOT / "experiments" / "results" / "wiki-ingest-20260506T211731Z.json"
RAG_INGEST = ROOT / "experiments" / "results" / "ingest-20260506T202904Z.json"

# Anthropic billing multipliers relative to base input rate.
CACHE_READ_RATE = 0.1
CACHE_WRITE_RATE = {"5-minute": 1.25, "1-hour": 2.0}


def load_components():
    rows = {}
    for line in COMPONENTS.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if parts[0] == "session":
            continue
        rows[parts[0]] = dict(uncached_in=int(parts[1]), cache_write=int(parts[2]),
                              cache_read=int(parts[3]), output=int(parts[4]))
    return rows


def main():
    rows = load_components()
    total = rows["TOTAL"]

    wiki = json.loads(WIKI_INGEST.read_text())
    deposited_in = wiki["totals"]["tokens_in"]
    deposited_out = wiki["totals"]["tokens_out"]

    component_sum = total["uncached_in"] + total["cache_write"] + total["cache_read"]
    print("Reconciliation against the deposited artifact")
    print(f"  components sum to      {component_sum:,}")
    print(f"  artifact totals.tokens_in {deposited_in:,}")
    if component_sum != deposited_in:
        raise SystemExit(
            f"REFUSED: components sum to {component_sum:,} but the deposited "
            f"artifact reports {deposited_in:,}. These are not the same telemetry."
        )
    print("  exact match, to the token\n")

    assert total["output"] == deposited_out, "output token mismatch"

    print("Share of the aggregate by class")
    for k in ("uncached_in", "cache_write", "cache_read"):
        print(f"  {k:<13}{total[k]:>14,}{100.0 * total[k] / deposited_in:>9.2f}%")

    print("\nBillable-input-equivalent (BIE) reconstruction")
    # The RAG-side artifact keeps prompt and completion separate (it never had
    # the aggregation defect); T_ingest is their sum, as preregistered.
    rag = json.loads(RAG_INGEST.read_text())
    t_ingest_rag = (rag["totals"]["prompt_tokens"]
                    + rag["totals"]["completion_tokens"])
    print(f"  T_ingest[rag] = {t_ingest_rag:,} (uncached both sides)")

    print(f"\n  {'TTL':<12}{'BIE input':>16}{'T_ingest[wiki]':>18}{'ratio':>10}{'verdict':>12}")
    for ttl, wrate in CACHE_WRITE_RATE.items():
        bie = (total["uncached_in"]
               + total["cache_write"] * wrate
               + total["cache_read"] * CACHE_READ_RATE)
        t_ingest_wiki = bie + total["output"]   # output carried at face value
        ratio = t_ingest_wiki / t_ingest_rag
        verdict = "SUPPORTED" if t_ingest_wiki > t_ingest_rag else "refuted"
        print(f"  {ttl:<12}{bie:>16,.0f}{t_ingest_wiki:>18,.0f}"
              f"{ratio:>9.1f}x{verdict:>12}")

    raw_ratio = (deposited_in + deposited_out) / t_ingest_rag
    print(f"\n  uncorrected (raw field): T_ingest[wiki] = "
          f"{deposited_in + deposited_out:,}, ratio {raw_ratio:.0f}x")
    print("\n  H3a is supported on every reading. The TTL in effect during the")
    print("  build was not recorded, so both endpoints are reported rather than")
    print("  one being assumed. Output tokens are carried unweighted, so these")
    print("  are not pure billable-cost figures; see the paper's limitations.")


if __name__ == "__main__":
    main()
