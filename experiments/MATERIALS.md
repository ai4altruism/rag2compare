# Materials Manifest — what is public, what is fetchable, what cannot be shipped

Companion to the OSF registration for *Vector RAG vs LLM-Compiled Wiki: A
Preregistered Comparison on a Small Multi-Domain Research Corpus*. Defines
exactly which study materials are released, which a replicator must fetch,
which cannot be redistributed at all, and how to verify integrity.

**Registration:** https://osf.io/zemhp (DOI: 10.17605/OSF.IO/ZEMHP), registered
public 2026-05-06, before any judge run. Preregistration tag
`osf-prereg-2026-05-06`, commit `655ef12`.

**Preprint:** arXiv:2605.18490.

> [!] **Deposit status, verified 2026-07-31: the artifacts are not yet publicly
> retrievable.** The public registration `zemhp` currently has **zero files**
> attached (`GET /v2/registrations/zemhp/files/osfstorage/` returns
> `meta.total: 0`), and the project it was registered from, `j37b8`, is
> **private** (`401` unauthenticated). The paper states in three places that the
> artifacts are "deposited on OSF with SHA-256 hashes", and until the files are
> uploaded and made public that is not something a reviewer can act on. All ten
> artifacts exist locally and verify against their recorded hashes; what is
> missing is the upload, not the data. **This must be resolved before
> submission**, both because the claim is load-bearing for criterion 1 and
> because TMLR's Reproducibility certification cannot be awarded against an
> empty deposit.

## 1. Released — the reproducibility package

Everything needed to re-derive every number in the paper from the recorded model
outputs, with no API keys and no corpus PDFs.

**Run artifacts** (10 files, `experiments/results/`, deposited on OSF):

| Group | Files | What they carry |
|---|---|---|
| Preregistered | 5 | RAG + wiki ingest and run telemetry, and the primary judge run with Gemini IRR coverage |
| Post-hoc | 5 | claim-level grounding, the decomp-RAG run, its original single-judge scoring, its claim-level grounding, and the 2026-07-31 dual-judge rejudge |

`ARTIFACTS_MANIFEST.txt` records a description, byte size, and SHA-256 for each.
Verify with:

```bash
python - <<'PY'
import hashlib, re
from pathlib import Path
R = Path('experiments/results')
for name, want in re.findall(r'##\s+(\S+).*?sha256:\s+([0-9a-f]{64})',
                             (R/'ARTIFACTS_MANIFEST.txt').read_text(), re.S):
    p = R/name if (R/name).exists() else R/'post-hoc'/name
    got = hashlib.sha256(p.read_bytes()).hexdigest()
    print(('ok  ' if got == want else 'BAD '), name)
PY
```

Last run 2026-07-31: **10 of 10 verified, 0 mismatched.**

**Protocol and code** (this repository):

- `corpus.yaml` — the 24-paper manifest with domains, roles, and ingest order
- `questions.yaml` — the 13 evaluation questions across six tiers
- `rubric.yaml` — the four anchored 1–10 criteria and their level descriptions
- `corpus_dois.tsv` — DOIs for the corpus, with per-row match confidence
- `run_preregistered_analysis.py` — the full confirmatory analysis and both preregistered robustness checks
- `run_claim_grounding.py`, `run_claim_grounding_decomp.py` — the atomize-and-score pipelines
- `run_decomp_rag.py` — the decomp-RAG ablation
- `analyze_decomp_dual_judge.py` — the two-judge reanalysis of the ablation
- `build_doi_manifest.py`, `fetch_papers.py` — corpus resolution and retrieval
- `backend/scripts/judge_runs.py` — the judge harness, including the blinding and seed discipline

## 2. Fetchable — the 24 corpus papers

**Not redistributable.** The corpus is peer-reviewed papers and preprints whose
copyright sits with publishers and authors, so the package ships pointers rather
than PDFs. `corpus_dois.tsv` gives one row per paper, and `fetch_papers.py`
retrieves what licensing allows into the exact paths `corpus.yaml` expects:

```bash
python experiments/build_doi_manifest.py            # rebuild the DOI manifest
python experiments/fetch_papers.py --email you@example.org --dry-run
python experiments/fetch_papers.py --email you@example.org
```

Status as of 2026-07-31:

| Outcome | Count | Notes |
|---|---:|---|
| Auto-fetchable | 14 | arXiv, or an open-access copy registered with Unpaywall |
| Manual retrieval | 6 | DOI confirmed, no OA copy; needs institutional access. Mostly SSRN and IEEE |
| DOI unconfirmed | 4 | flagged `UNVERIFIED`; see below |

Of the 24 rows, 19 are `ok`, 1 is `CHECK`, and 4 are `UNVERIFIED`.

The four unconfirmed rows are marked `UNVERIFIED` in the manifest rather than
guessed at. `corpus.yaml` records abbreviated titles, and for these four no
candidate cleared both the title-similarity threshold and the author/year
corroboration:

- *lit-tag — A Shiny App for Adding Custom Tags and Notes to a Citation Database* (McElhany et al., 2026) — no Crossref or arXiv result at all
- *Biological Response of Eelgrass Epifauna to Elevated Ocean Alkalinity* (Jones et al., 2025)
- *Air-Sea Gas Exchange in Response to OAE in a Temperate Plankton Community* (Schneider et al., 2025)
- *Considerations for the Integration of RCTs and Real-World Data* (Qiu et al., 2026)

One further row carries `CHECK`, meaning a strong title match whose author list
disagrees: *Monitoring, Reporting, and Verification for Ocean Alkalinity
Enhancement* (Ho et al., 2023). The matched title is exact and the DOI is
almost certainly right; it wants one human glance to confirm.

> Why the manifest refuses to guess: a wrong DOI is worse than an absent one,
> because it sends a replicator confidently to the wrong paper. The resolver
> requires title similarity **and** agreement on author or year precisely because
> title similarity alone produced a false positive during construction, matching
> *Label-Only Membership Inference Attacks* to *Label-Only Membership Inference
> Attack against Node-Level Graph Neural Networks*, a different paper that merely
> begins with the same words. The author check caught it.

**Corrections go in `corpus_doi_overrides.tsv`, not in the manifest**, which is
generated and would discard hand edits on the next rebuild. Each override
records the confirming evidence alongside the DOI. One is currently applied: the
Label-Only paper, confirmed against arXiv metadata as Choquette-Choo, Tramer,
Carlini and Papernot, `10.48550/arXiv.2007.14321`.

## 3. Not released

- **The compiled wiki corpus.** The wiki side of the comparison was built from
  the same 24 papers inside a private knowledge base that also holds unrelated
  internal material. The compiled wiki pages the wiki arm actually cited are
  reproduced in the run artifacts as quoted excerpts, so the claim-level analysis
  is fully re-derivable, but the wiki repository itself is not published.
- **API keys.** None are needed to reproduce the analysis; they are needed only
  to regenerate answers or re-run judging from scratch.

## 4. Reproducing the analysis

No PDFs, no keys, no vector store. From deposited artifacts alone:

```bash
python -m venv .venv && . .venv/bin/activate
pip install numpy pymc pyyaml
PYTENSOR_FLAGS="cxx=" python experiments/run_preregistered_analysis.py
python experiments/analyze_decomp_dual_judge.py \
    --decomp-judged experiments/results/post-hoc/judged-20260731T145648Z.json
```

Verified 2026-07-31 on a machine with **no corpus PDFs present at all**
(`experiments/papers/` absent). The run reproduces the published values, including
the Bayesian posteriors in the robustness table: H1 `inter_paper_mapping`
judge-average posterior mean +5.589 with P(mu >= 2) = 0.967, the only cell
clearing the preregistered "strongly corroborated" bar; H1 `structural_integrity`
+1.500 at P = 0.283; H2 +0.522 at P = 0.660; latency ratio 6.59x; and the
bias=wiki `inter_paper_mapping` stratum at +5.75.

Sampling is seeded (`random_seed=42`, 4 chains x 2000 draws x 2000 tune), so the
posteriors are reproducible to the digits quoted in the paper.
