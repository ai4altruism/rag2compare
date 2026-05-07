# Run Artifacts — RAG vs LLM Wiki Experiment

This page lists the five JSON artifacts produced by the experiment and their integrity checksums. They are the complete run record — every per-paper ingestion log, every per-question answer, every judge score is in this bundle.

**Repository tag:** [`osf-prereg-2026-05-06`](https://github.com/ai4altruism/rag2compare/releases/tag/osf-prereg-2026-05-06) (commit `655ef12`)
**Generated:** 2026-05-06T23:01:06Z UTC

---

## Pipeline overview

The experiment produces five artifacts in two streams that meet at the judge step:

```
RAG side       Wiki side          Judge
──────────     ─────────          ─────
ingest-*.json  wiki-ingest-*.json
     │              │
     └──── run-*.json ──── wiki-run-*.json
                  │              │
                  └────► judged-*.json (primary + IRR)
```

Each stage's output is the next stage's input. The judge consumes the two `*-run-*.json` files and produces `judged-*.json`, which is the input to the H1/H2/H3 hypothesis tests.

---

## File inventory

| Filename | Size | Role | Description |
|---|---|---|---|
| [`ingest-20260506T202904Z.json`](#) | 10 KB | RAG ingest | Per-paper timing + chunk + token telemetry across the 24-paper corpus |
| [`run-20260506T221602Z.json`](#) | 262 KB | RAG run | 13 questions × 5 reranked sources each, with per-question prompt/completion/thinking-token counts |
| [`wiki-ingest-20260506T211731Z.json`](#) | 7 KB | Wiki ingest | Per-paper compilation telemetry across the 24-paper corpus (Wiki side) |
| [`wiki-run-20260506T205500Z.json`](#) | 190 KB | Wiki run | 13 questions answered against the compiled wiki, with per-question token telemetry |
| [`judged-20260506T225645Z.json`](#) | 62 KB | Judge + IRR | Primary judge (GPT-5.4) on all 13 questions + secondary judge (Gemini 2.5 Pro) on all 13 for inter-rater reliability, with per-question scores, aggregate means, and max-deltas |

> Replace each link target with the OSF download URL once the file is uploaded.

---

## Integrity verification

Each artifact's `sha256` is fixed at upload time. To verify an artifact wasn't altered:

```bash
sha256sum <filename>
```

| Filename | sha256 |
|---|---|
| `ingest-20260506T202904Z.json` | `4a5ff508dc449ecb934a40e643ed524d125e383ef10000564dfbf9b84db73c28` |
| `run-20260506T221602Z.json` | `eb295306f91e39b764a02d64c8b745591087aec9d5f5d727ef132ba28b98537d` |
| `wiki-ingest-20260506T211731Z.json` | `da22f3aded2b747ae360f9eda91d8a64bacd43406f7bdfc3fee144ff73b86657` |
| `wiki-run-20260506T205500Z.json` | `6c1da6be7f7d5655b24152b3636be81b2835a94a35f593572f86211c4294ce8b` |
| `judged-20260506T225645Z.json` | `b74f44a75252ec3696e07ac47bcb6edc93ba90187fe9db70763694766deab163` |

The plain-text manifest with the same checksums is available as `ARTIFACTS_MANIFEST.txt` in the same OSF Files section.

---

## Schema documentation

Every artifact is plain JSON with no proprietary encoding. Schema details:

- **`ingest-*.json`** and **`wiki-ingest-*.json`** — schema documented in [`docs/WIKI_SIDE_BRIEF.md`](https://github.com/ai4altruism/rag2compare/blob/osf-prereg-2026-05-06/docs/WIKI_SIDE_BRIEF.md) §6.
- **`run-*.json`** and **`wiki-run-*.json`** — schema documented in [`docs/WIKI_SIDE_BRIEF.md`](https://github.com/ai4altruism/rag2compare/blob/osf-prereg-2026-05-06/docs/WIKI_SIDE_BRIEF.md) §7. Each result has `id`, `tier`, `bias`, `text`, `answer`, `sources[]`, `metadata{}` matching the preregistered question taxonomy.
- **`judged-*.json`** — produced by [`backend/scripts/judge_runs.py`](https://github.com/ai4altruism/rag2compare/blob/osf-prereg-2026-05-06/backend/scripts/judge_runs.py); contains `judgments[]` (primary), `secondary.judgments[]`, `secondary.agreement` (per-criterion max-deltas), `aggregate.overall`, and `aggregate.by_tier`.

---

## Reproducing the analysis

Given the five artifacts and the rubric, the H1/H2/H3 hypothesis tests are deterministic. The tagged commit contains every input and every script:

```bash
git clone https://github.com/ai4altruism/rag2compare.git
cd rag2compare
git checkout osf-prereg-2026-05-06
# place all five JSON files in experiments/results/
# then re-aggregate from the judged artifact:
python3 -c "
import json
with open('experiments/results/judged-20260506T225645Z.json') as f:
    print(json.load(f)['aggregate'])
"
```

The mean-of-judges adjustment, the H1/H2 per-tier means, and the H3 cost ratios can all be recomputed from the five artifacts alone — no API access, no model spend.

---

## What's not in this bundle

The OSF Files section contains only the five canonical run artifacts above plus the two manifest documents. The repository's `experiments/results/` directory locally contained additional intermediate files (smoke-test outputs from system development, earlier-failed judge attempts) that are **deliberately excluded** from the OSF upload. None of those intermediate files contain analysis-relevant data; they were verified outside the registered analysis plan and disclosed in the OSF preregistration's foreknowledge section.
