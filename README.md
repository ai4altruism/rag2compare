# Rag2Compare

A production-grade Retrieval-Augmented Generation (RAG) system for querying PDF document corpora with grounded, cited answers — **and the harness for running a controlled experiment that compares it against an LLM Wiki** built outside this repo.

Upload PDFs, ask natural-language questions, and get streaming answers that cite their sources — page numbers, section headers, and relevance scores included. The system runs entirely self-hosted via Docker Compose; cloud APIs are used only for LLM/embedding/judge calls.

## What this project is

There are two layers worth understanding:

1. **A general-purpose RAG system** — the FastAPI backend, Next.js frontend, Qdrant vector store, and provider abstractions described below. This works as a standalone tool: upload PDFs, organize them into collections, ask questions, get cited answers.

2. **An experiment harness on top of that system.** The repo also ships a CLI suite (`rag2compare-ingest`, `rag2compare-run`, `rag2compare-judge`), a 24-paper corpus manifest, a 13-question evaluation set, and a four-criterion judge rubric. Together they execute a controlled head-to-head comparison between Vector RAG (this system) and an **LLM Wiki** — Karpathy's pre-compiled knowledge architecture, built externally — using the same answer model (Claude Opus 4.7 with `xhigh` extended thinking) on both sides.

The hypotheses we're testing:

- **H1 (Synthesis):** the LLM Wiki outperforms Vector RAG on multi-hop queries where the answer requires integrating 3+ papers, because the Wiki pre-compiles cross-paper relationships.
- **H2 (Fact retrieval):** Vector RAG matches or beats the LLM Wiki on point-source factual lookups (specific stats, exact ranges), because RAG retrieves raw chunks without lossy summarization.
- **H3 (Efficiency):** the LLM Wiki pays a high upfront cost at *ingest* time and a low per-*query* cost; Vector RAG inverts that. The crossover point depends on corpus size and query volume.

See [`experiments/README.md`](experiments/README.md) for the step-by-step procedure, CLI reference, and JSON artifact schemas. The LLM-Wiki side and the 24-paper corpus procurement guide live in the companion repo [`ai4altruism/wikikb`](https://github.com/ai4altruism/wikikb) — you need both repos to reproduce the comparison.

## Architecture

```
┌─────────────────────────────────────┐
│  Next.js 15 Frontend  (port 3000)   │
│  Chat · Documents · Collections ·   │
│  Settings                           │
└────────────────┬────────────────────┘
                 │ REST + WebSocket
┌────────────────▼────────────────────┐
│  FastAPI Backend  (port 8000)       │
│                                     │
│  Ingestion pipeline                 │
│    Docling PDF parsing              │
│    Document-aware chunking          │
│    Contextual enrichment            │
│    Dense + sparse embedding         │
│                                     │
│  Query pipeline                     │
│    Multi-query expansion            │
│    Hybrid search (dense + BM25)     │
│    Reranking (Cohere / local)       │
│    Corrective RAG loop              │
│    Streaming answer generation      │
└──────┬───────────────────┬──────────┘
       │                   │
┌──────▼──────┐   ┌────────▼────────┐
│  Qdrant     │   │  SQLite         │
│  (port 6333)│   │  metadata DB    │
│  vectors +  │   │  documents,     │
│  sparse idx │   │  conversations  │
└─────────────┘   └─────────────────┘
```

All LLM, embedding, and reranking providers are swappable via configuration. Default providers: Anthropic **Claude Opus 4.7** with `xhigh` extended thinking (answer generation), Anthropic **Claude Sonnet 4.5** (per-chunk contextual enrichment during ingestion — cheaper model since summarization isn't reasoning-heavy), OpenAI `text-embedding-3-large` (embeddings), Cohere Rerank 3.5 (reranking). The experiment harness defaults to OpenAI **GPT-5** as the judge LLM (cross-family choice avoids same-family self-preference bias when scoring Claude outputs).

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Frontend framework | Next.js (App Router) | 15.3.1 |
| Frontend UI | shadcn/ui + Tailwind CSS | — |
| State management | Zustand | 5.x |
| Data fetching | TanStack Query | 5.x |
| Backend framework | FastAPI | >=0.115 |
| Backend language | Python | >=3.11 |
| PDF parsing | Docling (primary), PyMuPDF4LLM (fallback) | >=2.0 / >=0.0.17 |
| Vector database | Qdrant | latest (Docker) |
| Metadata database | SQLite (default) / PostgreSQL (optional) | — |
| ORM | SQLAlchemy 2.0 (async) | >=2.0.36 |
| LLM routing | LiteLLM | >=1.55 |
| Default answer model | Anthropic Claude Opus 4.7 (`xhigh` extended thinking, 32K thinking budget) | — |
| Default enrichment model | Anthropic Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) | — |
| Default judge model (experiment harness) | OpenAI GPT-5 with `medium` reasoning effort | — |
| Embeddings | OpenAI / Cohere / Sentence-Transformers / Ollama | — |
| Reranking | Cohere Rerank 3.5 / cross-encoder (local) | — |
| Package manager (backend) | uv | — |
| Package manager (frontend) | pnpm | — |

## Repository Layout

```
rag2compare/
├── backend/            FastAPI service (Python)
│   ├── src/            Application source
│   │   ├── api/        Route handlers and WebSocket endpoint
│   │   ├── config.py   Pydantic Settings (env vars + optional config.yaml)
│   │   ├── models/     SQLAlchemy ORM models
│   │   ├── pipelines/  Ingestion and query pipeline stages
│   │   ├── providers/  Pluggable LLM, embedding, and reranker providers
│   │   ├── schemas/    Pydantic request/response schemas
│   │   └── storage/    Qdrant client wrapper and DB session management
│   ├── tests/          pytest unit + integration tests
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/           Next.js application
│   ├── src/
│   │   ├── app/        App Router pages (/, /documents, /collections, /settings)
│   │   ├── components/ React components (chat, documents, layout, ui)
│   │   ├── lib/        API client and WebSocket client
│   │   ├── providers/  TanStack Query provider
│   │   └── stores/     Zustand stores
│   └── package.json
├── experiments/
│   ├── corpus.yaml     24-paper manifest (collections, role tags, file paths)
│   ├── questions.yaml  13 evaluation questions (5 tiers + 3 RAG-favoring)
│   ├── rubric.yaml     4-criterion judge rubric (1-10 anchored scales)
│   ├── papers/         PDFs go here, organized by domain (gitignored)
│   ├── results/        ingest-*.json / run-*.json / judged-*.json (gitignored)
│   └── README.md       Experiment workflow + artifact schemas
├── legacy/             v1 Streamlit prototype (preserved for reference, not active)
├── docker-compose.yml  Primary deployment configuration
├── .env.example        Environment variable template
└── data/               Runtime data — gitignored (uploads, metadata.db)
```

## Quickstart (Docker Compose)

This is the recommended way to run the full stack.

### Prerequisites

- Docker and Docker Compose
- API keys for your chosen providers (see [Environment Variables](#environment-variables))

### 1. Clone and configure

```bash
git clone https://github.com/ai4altruism/rag2compare.git
cd rag2compare
cp .env.example .env
```

Edit `.env` and fill in your API keys.

### 2. Start backend and Qdrant

The default compose profile starts the FastAPI backend and Qdrant only. The frontend is included under the `full` profile (see note below).

```bash
docker compose up
```

The backend API will be available at `http://localhost:8000`.
Interactive API docs are at `http://localhost:8000/docs`.
Qdrant dashboard is at `http://localhost:6333/dashboard`.

### 3. Start the full stack (backend + frontend + Qdrant)

```bash
docker compose --profile full up
```

The Next.js frontend will be available at `http://localhost:3000`. Inside the
compose network the frontend reaches the backend at `http://backend:8000` via
the `BACKEND_URL` env var; no extra configuration is needed.

### Optional: local LLM serving via Ollama

```bash
docker compose --profile local-llm up
```

This starts an Ollama container on port 11434. Configure `LLM_PROVIDER=ollama` and the desired model in `.env`.

## Local Development

### Backend

Requires Python >=3.11 and [uv](https://github.com/astral-sh/uv).

```bash
cd backend
uv sync
uv run uvicorn src.main:app --reload --port 8000
```

Run tests:

```bash
uv run pytest
```

Lint:

```bash
uv run ruff check src tests
```

### Frontend

Requires Node.js and [pnpm](https://pnpm.io).

```bash
cd frontend
pnpm install
pnpm dev
```

The dev server runs at `http://localhost:3000` and proxies API calls to `http://localhost:8000`.

## Environment Variables

Copy `.env.example` to `.env` and populate the values. All settings can also be overridden via a `config.yaml` file in the backend working directory (env vars take precedence).

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(required for default LLM)_ | Anthropic API key |
| `OPENAI_API_KEY` | _(required for default embeddings)_ | OpenAI API key |
| `COHERE_API_KEY` | _(required for default reranker)_ | Cohere API key |
| `LLM_PROVIDER` | `anthropic` | LLM provider (`anthropic`, `openai`, `ollama`, or any LiteLLM string) |
| `LLM_MODEL` | `claude-opus-4-7` | Answer-generation model identifier passed to LiteLLM |
| `ENRICHMENT_LLM_MODEL` | `claude-sonnet-4-5-20250929` | Per-chunk contextual enrichment model (cheaper than answer model). Set blank to reuse `LLM_MODEL`. |
| `REASONING_EFFORT` | `xhigh` | Anthropic adaptive-thinking effort tier: `off / low / medium / high / xhigh / max` (passed via `output_config.effort`). `xhigh` matches Claude Code's xhigh preset; `max` is the absolute ceiling. `off` omits the thinking block entirely. |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | Embedding model name |
| `EMBEDDING_DIMENSIONS` | `1024` | Vector dimensions |
| `RERANKER_PROVIDER` | `cohere` | Reranker provider (`cohere` or `cross-encoder`) |
| `RERANKER_MODEL` | `rerank-v3.5` | Reranker model name |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant connection URL |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

See `backend/src/config.py` for the full list of configurable settings, including ingestion parameters (parser selection, chunk size, contextual enrichment toggle) and retrieval parameters (top-k, RRF k, corrective RAG threshold, context expansion mode).

## API Reference

The backend exposes a REST API and a WebSocket endpoint. Endpoint groups:

| Group | Base path | Description |
|---|---|---|
| Documents | `/api/documents` | Upload, list, inspect, delete, re-ingest PDFs |
| Collections | `/api/collections` | Create and manage document collections |
| Query | `/api/query` | Submit queries (non-streaming REST) |
| Query streaming | `/ws/query` | Submit queries with token-by-token streaming via WebSocket |
| Conversations | `/api/conversations` | Create and retrieve conversation history |
| Settings | `/api/settings` | Read and update provider configuration |
| Health | `/api/health` | Dependency health check (Qdrant, LLM, embeddings) |

Full interactive documentation is auto-generated at `http://localhost:8000/docs` when the backend is running.

## Running the experiment

For the RAG vs LLM Wiki comparison, the workflow is:

```bash
# 0. Pre-flight: drop the 24 PDFs into experiments/papers/<domain>/
#    matching the filenames in experiments/corpus.yaml. The procurement
#    guide (DOIs, arXiv IDs, download URLs per paper) is in the companion
#    repo at github.com/ai4altruism/wikikb/blob/main/CORPUS.md.
docker compose --profile full up -d
curl -s http://localhost:8000/api/health | jq

# 1. Ingest the corpus (RAG side) — produces experiments/results/ingest-<ts>.json
cd backend
uv run rag2compare-ingest --manifest ../experiments/corpus.yaml

# 2. Run the question set (RAG side) — produces experiments/results/run-<ts>.json
uv run rag2compare-run --questions ../experiments/questions.yaml --reasoning-effort xhigh

# 3. (External) the LLM Wiki side runs the same papers and questions, producing
#    a wiki-ingest-<ts>.json and wiki-run-<ts>.json in compatible schemas.

# 4. Score both runs with a cross-family judge — produces judged-<ts>.json
uv run rag2compare-judge \
  --rag-run  ../experiments/results/run-<rag-ts>.json \
  --wiki-run ../experiments/results/wiki-run-<wiki-ts>.json \
  --rubric   ../experiments/rubric.yaml
```

[`experiments/README.md`](experiments/README.md) walks through every step including the inter-rater reliability spot-check and how each hypothesis maps to a check on the resulting JSON artifacts. The 24-paper corpus and the procurement guide (DOIs, arXiv IDs, download links) live in the companion repo — see [`CORPUS.md`](https://github.com/ai4altruism/wikikb/blob/main/CORPUS.md) in [`ai4altruism/wikikb`](https://github.com/ai4altruism/wikikb).

## Further Reading

- [experiments/README.md](experiments/README.md) — Step-by-step procedure, CLI reference, and JSON artifact schemas for the experiment
- [ai4altruism/wikikb](https://github.com/ai4altruism/wikikb) — Companion repo: the LLM-Wiki side of the experiment and the 24-paper corpus procurement guide (`CORPUS.md`)

## Project Status

Sprints 1–7 complete: full backend pipeline, Next.js frontend, Opus 4.7 extended-thinking integration, document tagging, token telemetry, and the three experiment CLIs (ingest, run, judge). Sprint 8 — additional RAG quality evaluation (RAGAS / DeepEval), expanded test coverage, vision-parser fallback, performance benchmarking, and Docker Compose production hardening — is the remaining work.

## License

GNU General Public License v3.0. Copyright (c) 2025 AI for Altruism Inc.

```
Rag2Compare
Copyright (c) 2025 AI for Altruism Inc
License: GNU GPL v3.0
```

## Contact

team@ai4altruism.org
