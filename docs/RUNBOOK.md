# Experiment Runbook

| Field | Value |
|---|---|
| **Document Version** | 1.0 |
| **Date** | 2026-05-04 |
| **Status** | As-built |
| **Companion documents** | [SRS.md](./SRS.md) · [SDP.md](./SDP.md) · [experiments/README.md](../experiments/README.md) |

This runbook is the step-by-step procedure for executing the **RAG vs.
LLM Wiki** experiment end-to-end against the rag2compare system. Follow
the phases in order; every command is reproducible and every output
artifact has a defined location and shape.

The experiment compares two knowledge architectures over a 24-paper
corpus across three domains (AI Ethics & Law, Climate Science,
Precision Medicine):

- **Condition A: Vector RAG** — this repo. Document-aware chunking,
  hybrid search (dense + sparse), reranking, corrective RAG,
  Opus 4.7 with `xhigh` extended thinking for answer generation.
- **Condition B: LLM Wiki** — built externally per Karpathy's
  agentic markdown architecture. Compiles knowledge into a persistent,
  cross-referenced wiki at ingest time.

Both systems answer the same 13-question evaluation set. A
cross-family judge (`gpt-5`) scores both outputs against the four
rubric criteria in `experiments/rubric.yaml`.

---

## Table of Contents

1. [Phase 0 — Pre-flight](#phase-0--pre-flight)
2. [Phase 1 — Ingestion](#phase-1--ingestion)
3. [Phase 2 — Query](#phase-2--query)
4. [Phase 3 — Judge](#phase-3--judge)
5. [Phase 4 — Analysis](#phase-4--analysis)
6. [Troubleshooting](#troubleshooting)
7. [Artifact reference](#artifact-reference)

---

## Phase 0 — Pre-flight

### 0.1 Prerequisites

Before starting:

- [ ] Docker and Docker Compose installed
- [ ] API keys for `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (embeddings),
      and `COHERE_API_KEY` (reranker). For the judge phase you will
      also need `OPENAI_API_KEY` valid for `gpt-5` (or whatever judge
      model you select).
- [ ] All 24 source PDFs available locally (filenames matching
      `experiments/corpus.yaml`)
- [ ] LLM Wiki side already built and capable of producing `run-*.json`
      artifacts in the same schema as the RAG runner produces

### 0.2 Configure the environment

```bash
cd rag2compare
cp .env.example .env
```

Edit `.env`:

| Variable | Required value | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | (your key) | Required for default LLM |
| `OPENAI_API_KEY` | (your key) | Required for embeddings + judge |
| `COHERE_API_KEY` | (your key) | Required for default reranker |
| `LLM_MODEL` | `claude-opus-4-7` | Default; matches the Wiki side's answer model |
| `ENRICHMENT_LLM_MODEL` | `claude-sonnet-4-5-20250929` | Cheaper model for per-chunk summarization during ingestion |
| `REASONING_EFFORT` | `xhigh` | Adaptive-thinking effort tier (`output_config.effort`); matches Claude Code's xhigh preset on the Wiki side. Other tiers: `off / low / medium / high / xhigh / max`. |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | Default |
| `RERANKER_MODEL` | `rerank-v3.5` | Default |

Confirm via:

```bash
grep -E '^(LLM_MODEL|REASONING_EFFORT|ENRICHMENT_LLM_MODEL)=' .env
```

### 0.3 Drop the corpus PDFs into place

```bash
cp /path/to/your/papers/ai-ethics-law/*.pdf  experiments/papers/ai-ethics-law/
cp /path/to/your/papers/climate-science/*.pdf experiments/papers/climate-science/
cp /path/to/your/papers/precision-medicine/*.pdf experiments/papers/precision-medicine/
```

The filenames must match the `file:` paths in `experiments/corpus.yaml`.
A dry-run will tell you exactly which paths are missing:

```bash
cd backend
uv run rag2compare-ingest --manifest ../experiments/corpus.yaml --dry-run
```

Iterate on filenames until the dry-run output shows every path with no
warning rows.

### 0.4 Start the stack

```bash
docker compose --profile full up -d
```

Wait ~30 seconds, then verify:

```bash
curl -s http://localhost:8000/api/health | jq
# Expect: status="ok", qdrant.status="ok",
#         embedding_provider.status="ok", llm_provider.status="ok"

curl -s http://localhost:8000/api/settings | jq '{llm_model, enrichment_llm_model, reasoning_effort}'
# Expect: llm_model="claude-opus-4-7", reasoning_effort="xhigh"
```

Open the UI to sanity-check:

- `http://localhost:3000/` — Chat (will be empty until ingestion)
- `http://localhost:3000/collections` — Collections (empty)
- `http://localhost:3000/settings` — Settings (should reflect `.env`)

### 0.5 Smoke-test ingestion + query (one paper)

Pick one paper as a smoke target — `stober_dornis_2026.pdf` is a good
choice (Anchor in ai-ethics-law).

```bash
cd backend
uv run rag2compare-ingest \
  --manifest ../experiments/corpus.yaml \
  --only stober_dornis_2026.pdf
```

Expected: status reaches `completed`, `ingestion_seconds` is a
positive float, no errors.

Smoke-query through the chat UI: select the `ai-ethics-law` collection,
ask a Tier-1 fact question about that paper, confirm the streaming
response cites Source 1 with a verbatim quote and that the metadata
badges show `thinking_tokens > 0` and `model_used: claude-opus-4-7`.

If anything in 0.5 fails, **stop here**. See [Troubleshooting](#troubleshooting).

---

## Phase 1 — Ingestion

DV measured: ingestion-time and ingestion-token cost per system.

### 1.1 Run the RAG ingestion

```bash
cd backend
uv run rag2compare-ingest --manifest ../experiments/corpus.yaml
```

This will:

- Create the three collections (`ai-ethics-law`, `climate-science`,
  `precision-medicine`) if missing.
- Sort each collection's documents by role (`Anchor → Chrono →
  Bridge → Conflict`).
- Upload each PDF with `tags_json` carrying `domain`, `role`,
  `year`, `authors`, `title`.
- Poll each document's status until terminal, capturing
  `ingestion_seconds` from the `IngestionJob` row.

Expected runtime: roughly 10–25 minutes for 24 papers depending on
PDF size and Sonnet 4.5 enrichment latency.

If it crashes mid-run, resume:

```bash
uv run rag2compare-ingest --manifest ../experiments/corpus.yaml --skip-completed
```

### 1.2 Verify the RAG ingestion artifact

```bash
ls -t experiments/results/ingest-*.json | head -1
cat $(ls -t experiments/results/ingest-*.json | head -1) | \
  jq '{total: .totals.documents, completed: .totals.completed, by_domain: .totals.by_domain}'
```

Expected:

```json
{
  "total": 24,
  "completed": 24,
  "by_domain": {
    "ai-ethics-law": { "documents": 8, "completed": 8, "total_seconds": <N> },
    "climate-science": { "documents": 8, "completed": 8, "total_seconds": <N> },
    "precision-medicine": { "documents": 8, "completed": 8, "total_seconds": <N> }
  }
}
```

If any document is in `error` status:

```bash
cat $(ls -t experiments/results/ingest-*.json | head -1) | \
  jq '.documents[] | select(.status != "completed")'
```

Investigate the `error_message`. Re-upload the offending paper via the
UI Documents page after fixing the source PDF.

### 1.3 Confirm Wiki ingestion artifact (or produce one)

The Wiki side must produce a per-paper ingestion log in compatible
shape. At minimum:

```json
{
  "started_at": "<ISO timestamp>",
  "documents": [
    { "filename": "<paper>.pdf",
      "domain": "ai-ethics-law",
      "role": "Anchor",
      "ingestion_seconds": <float>,
      "status": "completed",
      "tokens_in": <int, optional>,
      "tokens_out": <int, optional> }
  ],
  "totals": {
    "documents": 24,
    "completed": 24,
    "total_seconds": <float>,
    "by_domain": { ... }
  }
}
```

Save it as `experiments/results/wiki-ingest-<timestamp>.json`. Token
counts are optional but **highly recommended** — Hypothesis 3 (the
efficiency tradeoff) depends on them.

---

## Phase 2 — Query

DVs measured: groundedness, synthesis, conflict resolution per question
per system. Per-query token cost (recorded automatically on the RAG
side via `metadata.thinking_tokens` etc.).

### 2.1 Run the RAG question set

```bash
cd backend
uv run rag2compare-run \
  --questions ../experiments/questions.yaml \
  --reasoning-effort xhigh
```

This submits each of the 13 questions in a fresh conversation (no
cross-question memory contamination), records answer + sources +
metadata, writes `experiments/results/run-<ts>.json`.

Expected runtime: ~5–15 minutes depending on `xhigh` thinking latency
per question.

### 2.2 Spot-check three answers

Before committing the run to judging, eyeball three representative
outputs to catch obvious failures (empty answers, missing sources,
silently wrong model):

```bash
LATEST=$(ls -t experiments/results/run-*.json | head -1)

# Tier-1 (RAG-favoring)
jq '.results[] | select(.id == "B1-devote3-confidence-interval") | {answer, model: .metadata.model_used, latency: .metadata.latency_ms, thinking: .metadata.thinking_tokens, n_sources: (.sources | length)}' "$LATEST"

# Tier-3 (multi-hop, Wiki-favoring)
jq '.results[] | select(.id == "T3-mia-as-copyright-evidence") | {answer, model: .metadata.model_used, latency: .metadata.latency_ms, thinking: .metadata.thinking_tokens, n_sources: (.sources | length)}' "$LATEST"

# Bias-check
jq '.results[] | select(.id == "B2-he-tyka-equilibration-ratios") | {answer, model: .metadata.model_used, latency: .metadata.latency_ms, thinking: .metadata.thinking_tokens, n_sources: (.sources | length)}' "$LATEST"
```

For each, confirm:

- `model: "claude-opus-4-7"`
- `thinking > 0`
- `n_sources > 0`
- The `answer` text is non-empty and references at least one specific
  paper

### 2.3 Run the Wiki question set

The Wiki side runs the same 13 questions with the same model
(Opus 4.7 + xhigh) and produces a `run-<ts>.json` artifact in the
**same schema** as the RAG runner. Critical schema fields:

```json
{
  "results": [
    {
      "id": "<must match questions.yaml id exactly>",
      "tier": "<must match>",
      "bias": "<must match>",
      "text": "<question text>",
      "answer": "<wiki's answer>",
      "sources": [
        {
          "filename": "<source paper>.pdf or <wiki page>.md",
          "page_numbers": [<ints>] OR [],
          "chunk_text": "<verbatim excerpt>",
          "relevance_score": <float, optional>
        }
      ],
      "metadata": {
        "latency_ms": <int>,
        "prompt_tokens": <int, optional>,
        "completion_tokens": <int, optional>,
        "thinking_tokens": <int, optional>,
        "model_used": "claude-opus-4-7"
      }
    }
  ]
}
```

Save as `experiments/results/wiki-run-<timestamp>.json`. The judge
pairs by `id`, so the ids must match `experiments/questions.yaml`
exactly.

---

## Phase 3 — Judge

DV measured: rubric-scored quality on the four criteria for both
systems, per question and aggregated by tier.

### 3.1 Primary judge run

```bash
cd backend
uv run rag2compare-judge \
  --rag-run  ../experiments/results/run-<rag-ts>.json \
  --wiki-run ../experiments/results/wiki-run-<wiki-ts>.json \
  --rubric   ../experiments/rubric.yaml
```

The judge:

- Pairs questions by `id`.
- Per question, randomly assigns RAG→A,Wiki→B or RAG→B,Wiki→A
  (seeded; recorded in output for un-blinding).
- Sends question + both blinded answers + both source lists + the
  full rubric (with anchor definitions) to `gpt-5` with
  `reasoning_effort=medium`.
- Parses scored JSON and writes `experiments/results/judged-<ts>.json`.

Expected runtime: ~3–10 minutes for 13 questions on `gpt-5` medium.

### 3.2 Inter-rater reliability spot-check

Pick three questions across tiers (one Tier-1 / RAG-favoring, one
Tier-3 multi-hop, one bias-check) and re-judge with a second model:

```bash
uv run rag2compare-judge \
  --rag-run  ../experiments/results/run-<rag-ts>.json \
  --wiki-run ../experiments/results/wiki-run-<wiki-ts>.json \
  --rubric   ../experiments/rubric.yaml \
  --secondary-judge gemini-2.5-pro \
  --secondary-judge-questions T1-cardio-baselines,T3-mia-as-copyright-evidence,B1-devote3-confidence-interval
```

Inspect agreement:

```bash
LATEST_JUDGED=$(ls -t experiments/results/judged-*.json | head -1)
jq '.secondary.agreement.max_deltas' "$LATEST_JUDGED"
```

**Decision rule:** if any criterion's `max_delta > 2`, the primary
judge's calibration on that criterion is suspect. Either:

- Re-run the primary judge with a clearer rubric (tighten anchor
  definitions in `rubric.yaml`), OR
- Use the **mean of both judges** for that criterion in your final
  analysis, OR
- Add a third judge and take the median.

Document whichever path you take in the writeup.

### 3.3 Verify the judged artifact

```bash
LATEST_JUDGED=$(ls -t experiments/results/judged-*.json | head -1)

# All 13 questions scored, no parse errors
jq '.judgments | length' "$LATEST_JUDGED"
jq '[.judgments[] | select(.error != null)] | length' "$LATEST_JUDGED"

# Aggregate scores
jq '.aggregate.overall' "$LATEST_JUDGED"
```

Expected: 13 judgments, 0 errors, both systems with non-null mean
scores on every criterion.

---

## Phase 4 — Analysis

The hypotheses map directly to checks on the artifacts you now have.

### 4.1 H1 — Synthesis advantage (Wiki should win on multi-hop)

```bash
LATEST_JUDGED=$(ls -t experiments/results/judged-*.json | head -1)

jq '.aggregate.by_tier."multi-hop" | {
  rag_inter_paper:  .rag.inter_paper_mapping,
  wiki_inter_paper: .wiki.inter_paper_mapping,
  rag_structural:   .rag.structural_integrity,
  wiki_structural:  .wiki.structural_integrity
}' "$LATEST_JUDGED"

jq '.aggregate.by_tier.emergence | {
  rag_inter_paper:  .rag.inter_paper_mapping,
  wiki_inter_paper: .wiki.inter_paper_mapping
}' "$LATEST_JUDGED"
```

**H1 supported** if Wiki means exceed RAG means by ≥ 2.0 on
`inter_paper_mapping` and `structural_integrity` for the multi-hop
and emergence tiers. A smaller delta still supports H1 weakly; a
reversal is a strong negative result worth reporting.

### 4.2 H2 — Fact-retrieval baseline (RAG should match or beat on point-source)

```bash
jq '.aggregate.by_tier."bias-check" | {
  rag_groundedness:  .rag.groundedness,
  wiki_groundedness: .wiki.groundedness
}' "$LATEST_JUDGED"
```

**H2 supported** if RAG mean groundedness ≥ Wiki mean groundedness on
the `bias-check` tier. If RAG **loses** here, that's a strong negative
result — it would mean the chunking + retrieval pipeline is losing
point-source fidelity that even a "lossy" wiki can preserve.

### 4.3 H3 — Efficiency tradeoff (Wiki pays upfront, RAG pays per-query)

Combine artifacts:

```bash
RAG_INGEST=$(ls -t experiments/results/ingest-*.json | head -1)
WIKI_INGEST=$(ls -t experiments/results/wiki-ingest-*.json | head -1)
LATEST_RUN=$(ls -t experiments/results/run-*.json | head -1)
WIKI_RUN=$(ls -t experiments/results/wiki-run-*.json | head -1)

# Ingestion time (totals)
jq '.totals.total_seconds' "$RAG_INGEST"
jq '.totals.total_seconds' "$WIKI_INGEST"

# Per-query thinking-token totals
jq '[.results[].metadata.thinking_tokens // 0] | add' "$LATEST_RUN"
jq '[.results[].metadata.thinking_tokens // 0] | add' "$WIKI_RUN"

# Per-query latency (mean)
jq '[.results[].metadata.latency_ms] | add / length' "$LATEST_RUN"
jq '[.results[].metadata.latency_ms] | add / length' "$WIKI_RUN"
```

**H3 supported** if:

- Wiki total ingestion time and tokens substantially exceed RAG's, AND
- RAG total query-time tokens (especially `thinking_tokens` at
  `xhigh`) substantially exceed the Wiki's per-query cost.

The crossover point (papers needed before Wiki amortizes) is
`wiki_ingest_tokens / (rag_per_query_tokens - wiki_per_query_tokens)`.

### 4.4 Surprises and writeup

Pre-register the three hypotheses above before reading the
`judgments[].notes` field — the most valuable signal in this study is
**unexpected** patterns:

- A Wiki failure mode on a question where it should have excelled
- A RAG bias-check loss
- A criterion where the two judges strongly disagreed

For each surprise, file the supporting evidence (question id, both
answers, judge notes, scores) in your writeup. The judged JSON
contains everything you need.

---

## Troubleshooting

### Backend health check fails

```bash
docker compose logs backend | tail -50
```

- `Could not connect to Qdrant` → check `qdrant` service is up:
  `docker compose ps`. Restart with `docker compose restart qdrant`.
- `Could not authenticate to Anthropic / OpenAI / Cohere` → API key
  not loaded. Confirm `.env` is in the project root, has no trailing
  whitespace on values, and that you ran `docker compose up` from
  that directory (not from a subdirectory).

### Ingestion stuck in `parsing` for >10 minutes

Docling can be slow on scanned PDFs with OCR. Check logs:

```bash
docker compose logs backend | grep -i docling | tail -20
```

If it's truly stuck, kill the document:

```bash
curl -X DELETE "http://localhost:8000/api/documents/<doc-id>"
```

then re-upload via the UI with the PyMuPDF4LLM fallback parser
selected (or set `PARSER=pymupdf4llm` in `.env` and restart). PyMuPDF4LLM
is ~50x faster but loses some structural fidelity.

### Ingestion fails with "embedding dimensions mismatch"

If you've ingested papers with one embedding model and then changed
`EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS`, the new embeddings won't
match the existing Qdrant collection's vector schema. Either:

- Revert to the original embedding settings, OR
- Delete the affected collection (UI → Collections → trash icon) and
  re-ingest from scratch

### Judge response parsing errors

```bash
jq '.judgments[] | select(.error != null) | {question_id, error, raw_response}' \
  experiments/results/judged-<ts>.json
```

If a single question failed to parse, re-run with `--resume` pointing
at the same judged file. The judge re-runs only the missing/errored
questions.

```bash
uv run rag2compare-judge \
  --rag-run ../experiments/results/run-<rag-ts>.json \
  --wiki-run ../experiments/results/wiki-run-<wiki-ts>.json \
  --rubric ../experiments/rubric.yaml \
  --resume ../experiments/results/judged-<broken-ts>.json
```

If multiple questions fail with parse errors, the judge model may not
be honoring `response_format=json_object`. Try `--judge-model gpt-5`
explicitly, or fall back to `--judge-model gpt-4.1` which has very
reliable JSON-mode adherence.

### "No overlapping questions between the two runs"

The judge pairs by question `id`. Either:

- The Wiki run uses different ids — re-export with ids matching
  `experiments/questions.yaml` exactly.
- The RAG run was filtered (`--only-tier` or `--only-id`) — re-run
  without filters.

Confirm:

```bash
diff <(jq -r '.results[].id' experiments/results/run-<ts>.json | sort) \
     <(jq -r '.results[].id' experiments/results/wiki-run-<ts>.json | sort)
```

---

## Artifact reference

All artifacts live under `experiments/results/` and are gitignored.

| Filename | Producer | Schema | Used by |
|---|---|---|---|
| `ingest-<ts>.json` | `rag2compare-ingest` | per-doc timing + by-domain totals | Phase 1 verification, H3 analysis |
| `wiki-ingest-<ts>.json` | (Wiki side) | same shape as `ingest-*.json` | H3 analysis |
| `run-<ts>.json` | `rag2compare-run` | per-question answer + sources + metadata | Phase 3 input, H3 analysis |
| `wiki-run-<ts>.json` | (Wiki side) | same shape as `run-*.json` | Phase 3 input, H3 analysis |
| `judged-<ts>.json` | `rag2compare-judge` | per-question scores + aggregates | Phase 4 hypothesis tests |

See [experiments/README.md](../experiments/README.md) for full schema
details on each artifact.
