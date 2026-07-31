"""Fetch the 24 corpus PDFs from their DOIs, as far as licensing allows.

The corpus is 24 peer-reviewed papers and preprints. They cannot be
redistributed with the reproducibility package, so the package ships
`corpus_dois.tsv` and this script instead. Open-access papers download
automatically; paywalled ones are reported with their DOI links so a
replicator with institutional access can retrieve them by hand.

Files land at the exact `file:` paths `corpus.yaml` expects, so the ingest CLI
finds them without further configuration.

Nothing here defeats a paywall. Where no open-access copy is registered, the
script prints the DOI and moves on.

Run:
    python experiments/fetch_papers.py --email you@example.org
    python experiments/fetch_papers.py --email you@example.org --dry-run
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNPAYWALL = "https://api.unpaywall.org/v2"
ARXIV_PREFIX = "10.48550/arXiv."


def oa_pdf_url(doi: str, email: str) -> tuple[str, str]:
    """Return (pdf_url, provenance). Empty url means no OA copy is registered."""
    # arXiv DOIs resolve to a predictable PDF path, no lookup needed.
    if doi.startswith(ARXIV_PREFIX):
        return f"https://arxiv.org/pdf/{doi[len(ARXIV_PREFIX):]}", "arxiv"
    url = f"{UNPAYWALL}/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return "", f"unpaywall http {e.code}"
    except Exception as e:  # noqa: BLE001
        return "", f"unpaywall error: {type(e).__name__}"
    loc = data.get("best_oa_location") or {}
    pdf = loc.get("url_for_pdf") or ""
    if pdf:
        return pdf, f"unpaywall/{loc.get('host_type', 'oa')}"
    return "", "no OA copy registered"


def download(url: str, dest: Path, timeout: int = 60) -> tuple[bool, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "rag2compare-fetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}"
    if not body.startswith(b"%PDF"):
        return False, f"not a PDF ({len(body)} bytes; likely a landing page)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return True, f"{len(body):,} bytes"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=ROOT / "experiments" / "corpus_dois.tsv")
    ap.add_argument("--dest", type=Path, default=ROOT / "experiments",
                    help="root the manifest's file: paths are relative to")
    ap.add_argument("--email", required=True, help="contact address for the Unpaywall API")
    ap.add_argument("--dry-run", action="store_true", help="resolve links without downloading")
    ap.add_argument("--sleep", type=float, default=0.5)
    args = ap.parse_args()

    if not args.manifest.exists():
        print(f"missing {args.manifest}; run build_doi_manifest.py first", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(args.manifest.open(), delimiter="\t"))
    got, manual, skipped = [], [], []

    for r in rows:
        title, doi, status = r["title"], r["doi"], r["status"]
        dest = args.dest / r["file"]
        label = title[:52]

        if dest.exists():
            print(f"  have    {label:<52} {dest.name}")
            got.append(title)
            continue
        if not doi or status == "UNVERIFIED":
            print(f"  SKIP    {label:<52} no confirmed DOI ({r.get('note') or status})")
            skipped.append(title)
            continue

        url, prov = oa_pdf_url(doi, args.email)
        if not url:
            print(f"  manual  {label:<52} {prov} -> https://doi.org/{doi}")
            manual.append((title, doi))
            time.sleep(args.sleep)
            continue
        if args.dry_run:
            print(f"  would   {label:<52} [{prov}] {url}")
            got.append(title)
            time.sleep(args.sleep)
            continue

        ok, detail = download(url, dest)
        if ok:
            print(f"  fetched {label:<52} [{prov}] {detail}")
            got.append(title)
        else:
            print(f"  manual  {label:<52} download failed: {detail} -> https://doi.org/{doi}")
            manual.append((title, doi))
        time.sleep(args.sleep)

    print(f"\n{len(got)} available, {len(manual)} need manual retrieval, "
          f"{len(skipped)} have no confirmed DOI (of {len(rows)})")
    if manual:
        print("\nRetrieve these by hand, saving to the path in the manifest's file: column:")
        for t, d in manual:
            print(f"  https://doi.org/{d}   {t[:60]}")
    if skipped:
        print("\nNo confirmed DOI; resolve in corpus_dois.tsv first:")
        for t in skipped:
            print(f"  {t[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
