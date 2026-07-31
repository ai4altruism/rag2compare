"""Build the anonymized supplementary-material archive for double-blind review.

The submission PDF is anonymized by the TMLR stylefile plus an explicit
pdfauthor override. **The supplement is not covered by any of that**, and it is
uploaded to the same reviewers. A supplement built by zipping the repository
de-anonymizes the submission three separate ways:

  1. deposited artifacts embed absolute paths from the run machine, carrying
     the author's username (`/home/theo/...`);
  2. scripts carry a contact email;
  3. MATERIALS.md cites the public OSF DOI and the arXiv id, both of which
     resolve to the named author.

So this script stages the package, rewrites those, and then **verifies the
staged tree and refuses to write the archive if anything identifying remains**.
A scan that cannot fail is not a check.

Run:
    python experiments/build_supplement.py --out supplement.zip
    python experiments/build_supplement.py --out supplement.zip --with-artifacts
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments"

# Files shipped in every supplement. The corpus PDFs are never included.
PACKAGE = [
    "MATERIALS.md", "corpus.yaml", "questions.yaml", "rubric.yaml",
    "corpus_dois.tsv", "corpus_doi_overrides.tsv",
    "run_preregistered_analysis.py", "run_claim_grounding.py",
    "run_claim_grounding_decomp.py", "run_decomp_rag.py",
    "analyze_decomp_dual_judge.py", "build_doi_manifest.py",
    "fetch_papers.py",
]
# Note: this script is deliberately NOT in PACKAGE. It carries the identifying
# strings it scrubs, as its own rewrite and forbidden-pattern tables, so
# shipping the scrubber would leak exactly what it exists to remove. The scan
# below catches that if anyone adds it back.

# Substitutions applied to every staged text file, in order.
REWRITES = [
    # Collapse "https://osf.io/zemhp (DOI: 10.17605/OSF.IO/ZEMHP)" to one link
    # before the individual rules fire, or the substitution reads as
    # "[link] (DOI: [link])".
    (r"https?://osf\.io/zemhp\S*\s*\(DOI:\s*10\.17605/OSF\.IO/ZEMHP\)", "ANON_OSF_LINK"),
    (r"/(?:home|Users)/[A-Za-z0-9._-]+/", "/path/to/"),
    (r"[A-Za-z0-9._%+-]+@ai4altruism\.org", "anonymous@example.org"),
    (r"https?://(?:doi\.org/)?10\.17605/OSF\.IO/ZEMHP", "ANON_OSF_LINK"),
    (r"https?://osf\.io/zemhp\S*", "ANON_OSF_LINK"),
    (r"10\.17605/OSF\.IO/ZEMHP", "ANON_OSF_LINK"),
    (r"arXiv:\s*2605\.18490", "arXiv:ANONYMIZED"),
    (r"\bai4altruism\b", "anonymized-org"),
    (r"\btedcochran\b", "anonymized-user"),
]

# Anything matching these in the staged tree aborts the build.
FORBIDDEN = {
    "author surname": r"Cochran",
    "author given name": r"\bTheodore\b",
    "home directory": r"/(?:home|Users)/(?!path/to)[A-Za-z0-9._-]+",
    "org name": r"ai4altruism|AI for Altruism|\bA4A\b",
    "public OSF id": r"10\.17605|osf\.io/zemhp|ZEMHP",
    "public arXiv id": r"2605\.18490",
    "github user": r"tedcochran",
    "private wiki repo": r"\boffload\b",
}

TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".tsv", ".txt", ".json"}


def rewrite(text: str, anon_link: str) -> str:
    for pat, repl in REWRITES:
        text = re.sub(pat, repl, text)
    return text.replace("ANON_OSF_LINK", anon_link)


def stage(dest: Path, anon_link: str, with_artifacts: bool) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    written = []

    for name in PACKAGE:
        src = EXP / name
        if not src.exists():
            print(f"  warning: {name} missing, skipped", file=sys.stderr)
            continue
        (dest / name).write_text(rewrite(src.read_text(), anon_link))
        written.append(name)

    if with_artifacts:
        results_src = EXP / "results"
        man = results_src / "ARTIFACTS_MANIFEST.txt"
        if man.exists():
            (dest / "results").mkdir(exist_ok=True)
            (dest / "results" / man.name).write_text(rewrite(man.read_text(), anon_link))
            written.append("results/ARTIFACTS_MANIFEST.txt")
        for src in sorted(results_src.rglob("*.json")):
            rel = src.relative_to(results_src)
            out = dest / "results" / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            # Artifacts are JSON: rewrite as text so embedded run paths are
            # scrubbed, then re-serialize to confirm it is still valid JSON.
            cleaned = rewrite(src.read_text(), anon_link)
            json.loads(cleaned)
            out.write_text(cleaned)
            written.append(f"results/{rel}")

    return written


def scan(root: Path) -> list[tuple[str, str, str]]:
    findings = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = p.read_text(errors="replace")
        for label, pat in FORBIDDEN.items():
            for m in re.finditer(pat, text):
                line = text.count("\n", 0, m.start()) + 1
                findings.append((str(p.relative_to(root)), f"{label} (line {line})", m.group(0)))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "supplement.zip")
    ap.add_argument("--anon-link", default="[anonymized OSF view-only link]",
                    help="anonymized view-only link substituted for public OSF/arXiv ids")
    ap.add_argument("--with-artifacts", action="store_true",
                    help="include the run artifacts as well as code and docs")
    ap.add_argument("--keep-staging", action="store_true")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="supplement-"))
    staging = tmp / "supplement"
    print(f"staging -> {staging}")
    written = stage(staging, args.anon_link, args.with_artifacts)
    print(f"  {len(written)} file(s) staged")

    findings = scan(staging)
    if findings:
        print(f"\nREFUSING TO BUILD: {len(findings)} identifying string(s) in the staged tree")
        for path, label, snippet in findings[:25]:
            print(f"  {path}: {label} -> {snippet!r}")
        print("\nAdd a rewrite rule or remove the file, then rebuild.")
        return 1
    print("  anonymization scan: clean")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(staging.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(staging.parent))
    size = args.out.stat().st_size
    print(f"\nwrote {args.out}  ({size / 1_048_576:.1f} MiB, {len(written)} files)")
    if size > 100 * 1_048_576:
        print("  WARNING: over the 100 MB supplementary-material limit")

    if args.keep_staging:
        print(f"  staging kept at {staging}")
    else:
        shutil.rmtree(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
