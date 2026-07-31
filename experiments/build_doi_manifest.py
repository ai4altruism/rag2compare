"""Resolve the 24 corpus papers to DOIs and write a redistributable manifest.

The corpus PDFs cannot be redistributed (copyright), so the reproducibility
package ships a manifest plus `fetch_papers.py` instead. `corpus.yaml` records
title, authors, and year but no DOIs, so this script resolves them against
Crossref and records how confident each match is.

Matching is deliberately conservative: a Crossref result is only accepted as
`ok` when the normalized title similarity clears --threshold. Anything below it
is written as `UNVERIFIED` with the best candidate alongside, for a human to
confirm or correct. A wrong DOI in a reproducibility package is worse than an
absent one, because it sends a replicator to the wrong paper without telling
them.

Run:
    python experiments/build_doi_manifest.py --out experiments/corpus_dois.tsv
"""
import argparse
import difflib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CROSSREF = "https://api.crossref.org/works"
# Crossref asks for a contact address in the polite pool; this is the paper's
# public corresponding address.
MAILTO = "theo@ai4altruism.org"
UA = f"rag2compare-doi-manifest/1.0 (mailto:{MAILTO})"


def normalize(s: str) -> str:
    """Lowercase, strip punctuation and articles, collapse whitespace."""
    s = s.lower()
    s = re.sub(r"[‐-―]", "-", s)  # unicode dashes to ascii
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(the|a|an|of|for|in|on|and|to|with)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    """Similarity that tolerates the corpus's abbreviated titles.

    corpus.yaml records shortened titles, often "Short Name — Subtitle" where
    the published title is longer. A plain sequence ratio punishes that: the
    right paper scores low purely because the candidate has more words. So we
    also score the candidate truncated to the corpus title's length, and treat
    full containment as decisive.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na in nb:
        return 0.97
    full = difflib.SequenceMatcher(None, na, nb).ratio()
    head = difflib.SequenceMatcher(None, na, nb[: len(na)]).ratio()
    return max(full, head)


def surnames(authors: str) -> list[str]:
    """Pull likely surnames out of corpus.yaml's freeform author strings.

    Handles "Stober & Dornis", "Ranjan et al.", "Choquette-Choo et al.".
    """
    cleaned = re.sub(r"\bet al\.?", " ", authors)
    parts = re.split(r"[,&]|\band\b", cleaned)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def corroborate(corpus_authors: str, corpus_year, cand_authors: list[str],
                cand_year: int | None) -> tuple[bool, bool]:
    """Does the candidate agree with the corpus on first author and year?

    Title similarity alone is not enough. A longer published title that merely
    *starts with* the corpus's abbreviated title is frequently a different
    paper: "Label-Only Membership Inference Attacks" is contained in
    "Label-Only Membership Inference Attacks and Defenses in Semantic
    Segmentation Models", which is a different work by different authors. So a
    match is only accepted when the bibliography agrees too.
    """
    want = surnames(corpus_authors)
    hay = " ".join(cand_authors).lower()
    author_ok = bool(want) and any(w.split()[-1].lower() in hay for w in want)
    try:
        year_ok = cand_year is not None and abs(int(cand_year) - int(corpus_year)) <= 1
    except (TypeError, ValueError):
        year_ok = False
    return author_ok, year_ok


def query_crossref(title: str, author: str, rows: int = 5) -> list[dict]:
    params = {"query.bibliographic": title, "rows": str(rows), "mailto": MAILTO}
    if author:
        # Strip "et al." and "&" so the author query is a plain surname list.
        params["query.author"] = re.sub(r"\bet al\.?|&", " ", author).strip()
    url = f"{CROSSREF}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["message"]["items"]


def split_variants(title: str) -> list[str]:
    """Query variants: the full title, and the part before a dash subtitle."""
    out = [title]
    head = re.split(r"\s+[—–-]\s+", title, maxsplit=1)[0]
    if head and head != title and len(head) > 12:
        out.append(head)
    return out


def best_match(title: str, author: str) -> tuple[dict | None, float]:
    best, best_score = None, 0.0
    for variant in split_variants(title):
        try:
            items = query_crossref(variant, author)
        except Exception as e:  # noqa: BLE001
            print(f"    crossref error: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        for it in items:
            cand = (it.get("title") or [""])[0]
            if not cand:
                continue
            score = similarity(title, cand)
            if score > best_score:
                best, best_score = it, score
        if best_score >= 0.9:
            break
        time.sleep(0.2)
    return best, best_score


def query_arxiv(title: str) -> tuple[str, str, float]:
    """Fall back to arXiv for preprints Crossref does not index.

    The corpus inclusion criteria admit arXiv preprints, and arXiv mints a DOI
    of the form 10.48550/arXiv.<id> for every submission, so an arXiv hit is a
    citable DOI like any other.
    """
    q = urllib.parse.urlencode({
        "search_query": f'ti:"{title}"', "max_results": "5",
        "sortBy": "relevance",
    })
    url = f"https://export.arxiv.org/api/query?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return "", "", 0.0
    best = {"doi": "", "title": "", "score": 0.0, "authors": [], "year": None}
    for entry in re.findall(r"<entry>(.*?)</entry>", body, re.S):
        m_id = re.search(r"<id>https?://arxiv\.org/abs/([^<]+)</id>", entry)
        m_t = re.search(r"<title>(.*?)</title>", entry, re.S)
        if not (m_id and m_t):
            continue
        cand = re.sub(r"\s+", " ", m_t.group(1)).strip()
        score = similarity(title, cand)
        if score > best["score"]:
            aid = re.sub(r"v\d+$", "", m_id.group(1))
            m_y = re.search(r"<published>(\d{4})-", entry)
            best = {
                "doi": f"10.48550/arXiv.{aid}",
                "title": cand,
                "score": score,
                "authors": re.findall(r"<name>([^<]+)</name>", entry),
                "year": int(m_y.group(1)) if m_y else None,
            }
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=ROOT / "experiments" / "corpus.yaml")
    ap.add_argument("--out", type=Path, default=ROOT / "experiments" / "corpus_dois.tsv")
    ap.add_argument("--threshold", type=float, default=0.75,
                    help="normalized title similarity required to accept a match")
    ap.add_argument("--sleep", type=float, default=0.5, help="seconds between Crossref calls")
    ap.add_argument("--overrides", type=Path,
                    default=ROOT / "experiments" / "corpus_doi_overrides.tsv",
                    help="human-confirmed DOIs, applied in place of automated resolution")
    args = ap.parse_args()

    overrides: dict[str, tuple[str, str]] = {}
    if args.overrides.exists():
        for line in args.overrides.read_text().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0] != "title":
                overrides[parts[0].strip()] = (parts[1].strip(),
                                               parts[2].strip() if len(parts) > 2 else "")
        if overrides:
            print(f"loaded {len(overrides)} manual override(s) from {args.overrides.name}\n")

    corpus = yaml.safe_load(args.corpus.read_text())
    rows, n_ok, n_unverified = [], 0, 0

    for coll in corpus["collections"]:
        for doc in coll["documents"]:
            t = doc["tags"]
            title, author = str(t.get("title", "")), str(t.get("authors", ""))
            print(f"  {title[:60]:<60} ", end="", flush=True)
            year = t.get("year", "")

            if title in overrides:
                doi, note = overrides[title]
                n_ok += 1
                print(f"{'':>4}  {doi}  [override]")
                rows.append({
                    "domain": t.get("domain", ""), "role": t.get("role", ""),
                    "year": year, "authors": author, "title": title, "doi": doi,
                    "match_score": "", "status": "ok", "note": note or "manual override",
                    "source": "override", "matched_title": "", "file": doc.get("file", ""),
                })
                continue

            item, score = best_match(title, author)
            doi = (item or {}).get("DOI", "")
            matched = ((item or {}).get("title") or [""])[0]
            source = "crossref"
            cand_authors = [a.get("family", "") for a in (item or {}).get("author", []) or []]
            cand_year = None
            parts = ((item or {}).get("issued", {}) or {}).get("date-parts") or [[None]]
            if parts and parts[0]:
                cand_year = parts[0][0]

            if not doi or score < args.threshold:
                ax = query_arxiv(title)
                if ax["doi"] and ax["score"] > score:
                    doi, matched, score, source = ax["doi"], ax["title"], ax["score"], "arxiv"
                    cand_authors, cand_year = ax["authors"], ax["year"]

            author_ok, year_ok = corroborate(author, year, cand_authors, cand_year)
            if not doi or score < args.threshold:
                status, why = "UNVERIFIED", "no title match"
            elif not (author_ok or year_ok):
                status, why = "UNVERIFIED", "title matched but author and year both disagree"
            elif not author_ok:
                status, why = "CHECK", "year agrees, author does not"
            elif not year_ok:
                status, why = "CHECK", "author agrees, year does not"
            else:
                status, why = "ok", ""

            if status == "ok":
                n_ok += 1
                print(f"{score:.2f}  {doi}  [{source}]")
            else:
                n_unverified += 1
                print(f"{score:.2f}  {status:<10} {why or ('best: ' + (matched[:40] or 'no result'))}")
            rows.append({
                "domain": t.get("domain", ""),
                "role": t.get("role", ""),
                "year": t.get("year", ""),
                "authors": author,
                "title": title,
                "doi": doi,
                "match_score": f"{score:.3f}",
                "status": status,
                "note": why,
                "matched_title": matched,
                "source": source,
                "file": doc.get("file", ""),
            })
            time.sleep(args.sleep)

    cols = ["domain", "role", "year", "authors", "title", "doi",
            "match_score", "status", "note", "source", "matched_title", "file"]
    def cell(v) -> str:
        """One TSV cell: no tabs, no newlines, no markup.

        Crossref titles carry embedded newlines and HTML (<i>Phyllaplysia
        taylori</i>), which silently split one record across several lines and
        corrupt every downstream reader.
        """
        s = re.sub(r"<[^>]+>", "", str(v))
        return re.sub(r"\s+", " ", s).strip()

    with args.out.open("w") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(cell(r[c]) for c in cols) + "\n")

    print(f"\nwrote {args.out}  ({len(rows)} papers: {n_ok} resolved, "
          f"{n_unverified} needing manual confirmation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
