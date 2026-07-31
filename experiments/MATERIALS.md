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
| Auto-fetchable | 17 | arXiv, or an open-access copy registered with Unpaywall |
| Manual retrieval | 7 | DOI confirmed, no OA copy; needs institutional access. Mostly SSRN and IEEE |
| DOI unconfirmed | 0 | — |

**All 24 rows are `ok` as of 2026-07-31.** Six were settled by hand and recorded in
`corpus_doi_overrides.tsv` with their confirming evidence.

Six rows could not be settled automatically and were confirmed by hand against
Crossref and arXiv metadata, checking first author and year in each case. All
are recorded in `corpus_doi_overrides.tsv` with the evidence:

| Paper | DOI | Why automation missed it |
|---|---|---|
| Ho et al., 2023, MRV for OAE | `10.5194/sp-2-oae2023-12-2023` | Title matched exactly; the author check failed on a parsing artifact |
| Jones et al., 2025, eelgrass epifauna | `10.5194/bg-22-1615-2025` | The corpus records a short form of a published title that names two study species |
| Schneider et al., 2025, air-sea gas exchange | `10.5194/egusphere-2025-524` | Published title is much longer than the corpus's short form. **This is the EGUsphere preprint**; swap if a final journal version was the one ingested |
| Qiu et al., 2026, RCTs and real-world data | `10.48550/arXiv.2604.10308` | Not indexed by Crossref; the automated pass surfaced unrelated economics trial registrations |
| McElhany et al., 2026, lit-tag | `10.48550/arXiv.2603.19238` | Published as "lit-tag: An app for..." against the corpus's "lit-tag — A Shiny App for...". Distinct from `10.70212/cdrxiv.2026519.v1`, a related database paper on which McElhany is third author |
| Choquette-Choo et al., 2021, label-only MIA | `10.48550/arXiv.2007.14321` | Automation matched a different paper sharing the title prefix; the author check caught it |

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
