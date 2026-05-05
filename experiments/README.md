# Experiments

This directory drives the **RAG vs. LLM Wiki** comparison: 24 research papers
across three domains (AI Ethics & Law, Climate Science, Precision Medicine),
ingested into rag2compare and queried with a fixed eval set so the JSON
results can be compared against a parallel run on the LLM Wiki side.

## Layout

```
experiments/
├── corpus.yaml          24-paper manifest (collections, role tags, file paths)
├── questions.yaml       13 evaluation questions (5 tiers + 3 RAG-favoring)
├── rubric.yaml          4-criterion judge rubric (1-10 anchored)
├── papers/              PDFs go here, organized by domain (gitignored)
│   ├── ai-ethics-law/
│   ├── climate-science/
│   └── precision-medicine/
├── results/             ingest-<ts>.json, run-<ts>.json, judged-<ts>.json (gitignored)
└── README.md            this file
```

`papers/` and `results/` are gitignored. Drop the PDFs into the per-domain
folders matching the `file:` paths in `corpus.yaml`. The ingest CLI prints
which expected paths are missing.

## Prerequisites

1. Backend running locally (`docker compose up backend qdrant`) or somewhere
   reachable.
2. `.env` configured with at minimum `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
   (for embeddings), and `COHERE_API_KEY` (for reranking). Defaults already
   target Claude Opus 4.7 with `REASONING_EFFORT=xhigh`; see `.env.example`.
3. Backend Python deps installed (`uv sync` or equivalent) — both CLIs use
   `httpx + pyyaml` only and are also available as console scripts:
   `rag2compare-ingest` and `rag2compare-run`.

## Step 1 — Ingest the corpus

```bash
cd backend
rag2compare-ingest --manifest ../experiments/corpus.yaml
# or, equivalent:
python -m scripts.ingest_corpus --manifest ../experiments/corpus.yaml
```

What this does, in order:

1. Reads `corpus.yaml`, validates that every `file:` exists on disk.
2. Creates the three collections via `POST /api/collections` if missing.
3. Sorts each collection's documents by role using `ingest_order`
   (Anchor → Chrono → Bridge → Conflict by default).
4. Uploads each PDF via `POST /api/documents/upload` with `tags_json`
   carrying domain/role/year/authors.
5. Polls `GET /api/documents/{id}` until terminal status, capturing
   `ingestion_seconds` (joined from the latest `IngestionJob`).
6. Writes `experiments/results/ingest-<timestamp>.json` — your
   per-paper timing artifact for comparison against the Wiki run.

Useful flags:

| Flag                  | Purpose                                                                 |
| --------------------- | ----------------------------------------------------------------------- |
| `--base-url`          | Backend URL (default `http://localhost:8000`)                           |
| `--only SUBSTR`       | Filter to one PDF for smoke testing                                     |
| `--skip-completed`    | Skip docs already in `completed` status (resume after interruption)     |
| `--poll-interval`     | Seconds between status polls (default 2.0)                              |
| `--poll-timeout`      | Per-document timeout (default 1800s = 30min, generous for Docling)      |
| `--dry-run`           | Print the planned ingestion order without uploading                     |

## Step 2 — Run the eval question set

```bash
rag2compare-run --questions ../experiments/questions.yaml
# or:
python -m scripts.run_experiment --questions ../experiments/questions.yaml
```

For each question:

1. Looks up the requested collection names → ids via `GET /api/collections`.
2. Submits a fresh `POST /api/query` (no conversation history — avoids the
   "memory contamination" the experimental design warns about).
3. Captures answer, sources (with verbatim chunk text + page numbers +
   relevance scores), and metadata (latency, prompt/completion/thinking
   token counts, model_used, retrieval_count).
4. Writes `experiments/results/run-<timestamp>.json` with everything.

Useful flags:

| Flag                  | Purpose                                                                                |
| --------------------- | -------------------------------------------------------------------------------------- |
| `--reasoning-effort`  | Override Anthropic extended-thinking budget (`off / low / medium / high / xhigh`)      |
| `--collections`       | Comma-separated collection names; restricts each question's collections to this subset |
| `--repeat N`          | Ask each question N times (consistency / Tier-2 stability checks)                      |
| `--only-tier TIER`    | Run only one tier (e.g. `--only-tier multi-hop`)                                       |
| `--only-id ID`        | Run a single question by id                                                            |
| `--dry-run`           | Print the planned questions without submitting                                         |

## Question design

Twelve questions across five Wiki-leaning tiers and three RAG-favoring
bias-checks, per the experimental design:

| Tier            | Bias    | Count | What it tests                                                  |
| --------------- | ------- | ----- | -------------------------------------------------------------- |
| `chronological` | neutral | 2     | Updating stale knowledge vs. appending                         |
| `conflict`      | wiki    | 2     | Linting / contradiction detection                              |
| `multi-hop`     | wiki    | 2     | Synthesis across 3+ documents                                  |
| `emergence`     | wiki    | 2     | Identifying gaps / orphaned ideas                              |
| `policy`        | wiki    | 2     | Compiled mental-model recommendations                          |
| `bias-check`    | rag     | 3     | Point-source retrieval (specific stats / quoted ranges) — RAG should excel here |

Edit `questions.yaml` freely; the runner accepts any valid question shape.

## Output schema

`ingest-<ts>.json`:

```json
{
  "started_at": "20260504T200000Z",
  "manifest": ".../corpus.yaml",
  "backend_url": "http://localhost:8000",
  "documents": [
    { "filename": "...pdf", "domain": "...", "role": "Anchor",
      "ingestion_seconds": 47.2, "chunk_count": 38, "status": "completed" }
  ],
  "totals": {
    "documents": 24, "completed": 24, "total_seconds": 920.4,
    "by_domain": { "ai-ethics-law": { "documents": 8, "completed": 8, "total_seconds": 280.1 } }
  }
}
```

`run-<ts>.json`:

```json
{
  "started_at": "20260504T210000Z",
  "questions_path": ".../questions.yaml",
  "backend_url": "http://localhost:8000",
  "reasoning_effort": "xhigh",
  "repeat": 1,
  "results": [
    {
      "id": "T3-mia-as-copyright-evidence",
      "tier": "multi-hop",
      "bias": "wiki",
      "answer": "...",
      "sources": [ { "filename": "...", "page_numbers": [4,5], "chunk_text": "...", "relevance_score": 0.94 } ],
      "metadata": { "latency_ms": 18432, "prompt_tokens": 4031, "completion_tokens": 612,
                    "thinking_tokens": 18044, "model_used": "claude-opus-4-7" }
    }
  ]
}
```

## Step 3 — Score against the Wiki run with a judge LLM

```bash
rag2compare-judge \
  --rag-run experiments/results/run-<rag-ts>.json \
  --wiki-run path/to/wiki-run.json \
  --rubric experiments/rubric.yaml
# or:
python -m scripts.judge_runs --rag-run ... --wiki-run ... --rubric ...
```

What it does:

1. Loads both runs and pairs them by question `id` (warns about
   anything that doesn't match).
2. For each pair, blinds the answers as System A / System B with a
   seeded RNG. The mapping is recorded in the output so results stay
   un-blindable for analysis.
3. Submits the question, both blinded answers, both source lists, and
   the rubric (with anchor definitions) to the Judge LLM. Demands a
   structured JSON response.
4. Parses scores per system per criterion, plus a notes field. Records
   the full raw response for audit.
5. Computes per-system, per-criterion, and per-tier means.
6. Writes `experiments/results/judged-<timestamp>.json`.

**Default judge: `gpt-5` (cross-family).** Using Claude to judge Claude
has documented self-preference bias, so the judge defaults to OpenAI's
flagship. Override with `--judge-model` if you need something else.

**Wiki run shape.** The Wiki run JSON must use the same schema as the
RAG runner produces — `{"results": [{"id", "tier", "bias", "text",
"answer", "sources": [...], "metadata": {...}}, ...]}`. Sources should
include at least `filename`, `page_numbers`, `chunk_text`, and
`relevance_score` so the judge can verify groundedness against the same
shape it sees on the RAG side.

Useful flags:

| Flag                          | Purpose                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------ |
| `--judge-model`               | Primary judge (default `gpt-5`)                                                      |
| `--reasoning-effort`          | `low` / `medium` / `high` (default `medium` — judging is less reasoning-heavy)       |
| `--secondary-judge MODEL`     | Run a second judge for inter-rater reliability                                       |
| `--secondary-judge-questions` | Comma-separated question ids the secondary judge should re-score                     |
| `--seed`                      | RNG seed for blinding (default 42; same seed → same A/B mapping)                     |
| `--max-questions N`           | Cap (useful for cost-bounded smoke runs)                                             |
| `--resume PATH`               | Skip questions already scored by the same judge in a prior `judged-*.json`           |
| `--dry-run`                   | Print the planned judging without calling the LLM                                    |

### Inter-rater reliability spot-check

Pick 3 questions across the tiers and re-judge with a different family
to make sure the primary judge's calibration isn't drifting:

```bash
rag2compare-judge \
  --rag-run ... --wiki-run ... --rubric experiments/rubric.yaml \
  --secondary-judge gemini-2.5-pro \
  --secondary-judge-questions T1-cardio-baselines,T3-mia-as-copyright-evidence,B1-devote3-confidence-interval
```

The output's `secondary.agreement.max_deltas` field gives the worst
per-criterion delta between the two judges. Investigate any criterion
where the max delta exceeds 2.

### Output schema (`judged-<ts>.json`)

```json
{
  "judged_at": "20260504T220000Z",
  "rag_run": ".../run-<rag-ts>.json",
  "wiki_run": ".../wiki-run.json",
  "rubric": ".../rubric.yaml",
  "judge_model": "gpt-5",
  "reasoning_effort": "medium",
  "seed": 42,
  "criteria": ["groundedness", "structural_integrity", "conflict_awareness", "inter_paper_mapping"],
  "judgments": [
    {
      "question_id": "T3-mia-as-copyright-evidence",
      "tier": "multi-hop",
      "bias": "wiki",
      "blinding": { "A": "wiki", "B": "rag" },
      "rag_scores": { "groundedness": 7, "structural_integrity": 6, "conflict_awareness": 5, "inter_paper_mapping": 4 },
      "wiki_scores": { "groundedness": 8, "structural_integrity": 9, "conflict_awareness": 8, "inter_paper_mapping": 9 },
      "notes": "...",
      "raw_response": "...",
      "error": null
    }
  ],
  "aggregate": {
    "overall": { "n": 13, "rag": { ... }, "wiki": { ... } },
    "by_tier": { "multi-hop": { "n": 2, "rag": { ... }, "wiki": { ... } }, ... }
  },
  "secondary": null
}
```

## Comparison against the Wiki run — testing the hypotheses

With `judged-<ts>.json` in hand, the experiment's three hypotheses
become straightforward to evaluate:

- **H1 (Synthesis):** check that `aggregate.by_tier["multi-hop"].wiki`
  exceeds `.rag` on `inter_paper_mapping` and `structural_integrity`.
- **H2 (Fact retrieval):** check that `aggregate.by_tier["bias-check"].rag`
  meets or exceeds `.wiki` on `groundedness`.
- **H3 (Efficiency):** combine the `judged-*.json` aggregates with the
  `ingest-*.json` totals from Step 1 — Wiki should have the higher
  ingest cost; RAG should have the higher per-query cost (especially in
  thinking_tokens at xhigh effort, recorded in each query's metadata).
