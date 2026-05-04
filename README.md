# Rag2Compare

A production-grade Retrieval-Augmented Generation (RAG) system for querying PDF document corpora with grounded, cited answers.

Upload PDFs, ask natural-language questions, and get streaming answers that cite their sources — page numbers, section headers, and relevance scores included. The system runs entirely self-hosted via Docker Compose; cloud APIs are used only for LLM/embedding calls.

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

All LLM, embedding, and reranking providers are swappable via configuration. Default providers: Anthropic Claude (generation), OpenAI `text-embedding-3-large` (embeddings), Cohere Rerank 3.5 (reranking).

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
├── docs/
│   ├── SRS.md          System Requirements Specification (v2.0 source of truth)
│   └── SDP.md          Software Development Plan (sprint breakdown)
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

The Next.js frontend will be available at `http://localhost:3000`.

> **Note:** The frontend `Dockerfile` has not yet been added to the repository. The `--profile full` command will fail until it is created. Use the local development path below to run the frontend in the meantime.

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
| `LLM_MODEL` | `claude-sonnet-4-5-20250929` | Model identifier passed to LiteLLM |
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

## Further Reading

- [docs/SRS.md](docs/SRS.md) — Detailed functional and non-functional requirements, data model, and API specification
- [docs/SDP.md](docs/SDP.md) — Sprint plan, git workflow, definition of done, and risk register

## Project Status

The project is mid-development. Sprints 1-6 are complete (foundation, ingestion pipeline, query pipeline with streaming and corrective RAG, Next.js scaffold). Sprint 7 (frontend feature completion) and Sprint 8 (evaluation, E2E tests, Docker Compose production config, docs) are upcoming. See [docs/SDP.md](docs/SDP.md) for the full sprint plan.

## License

GNU General Public License v3.0. Copyright (c) 2025 AI for Altruism Inc.

```
Rag2Compare
Copyright (c) 2025 AI for Altruism Inc
License: GNU GPL v3.0
```

## Contact

team@ai4altruism.org
