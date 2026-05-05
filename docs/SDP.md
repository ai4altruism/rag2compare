# Software Development Plan (SDP)

## Rag2Compare v2.0

| Field | Value |
|---|---|
| **Document Version** | 1.1 |
| **Date** | 2026-05-04 |
| **Status** | As-built through Sprint 7 |
| **Companion Documents** | [SRS.md](./SRS.md) · [RUNBOOK.md](./RUNBOOK.md) |
| **Revision history** | 1.0 (2026-03-20) Draft · 1.1 (2026-05-04) Sprint 7 expanded to capture the four-PR experiment-readiness scope (backend foundations, batch ingestion + runner CLIs, frontend pull-forward, judge tooling); §1.3 phase mapping updated; §6 risk register expanded with R9–R11. |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Development Methodology](#2-development-methodology)
3. [Git Workflow](#3-git-workflow)
4. [Sprint Plan](#4-sprint-plan)
5. [Dependency Graph](#5-dependency-graph)
6. [Risk Register](#6-risk-register)
7. [Definition of Done](#7-definition-of-done)

---

## 1. Overview

### 1.1 Goals

Transform the existing Streamlit-based RAG prototype into a production-grade system with:
- FastAPI backend with provider-agnostic architecture
- Modern ingestion pipeline (Docling, document-aware chunking, contextual enrichment)
- Advanced query pipeline (hybrid search, dedicated reranking, corrective RAG)
- React/Next.js frontend with streaming chat
- Comprehensive evaluation and testing

### 1.2 Sprint Cadence

- **Sprint length**: 2 weeks
- **Total sprints**: 8 (16 weeks)
- **Phases**: 5 (mapped from SRS Section 10.1)

### 1.3 Phase-to-Sprint Mapping

| Phase | Name | Sprints | Status | Focus |
|---|---|---|---|---|
| 1 | Foundation | Sprints 1-2 | ✅ Complete | Project scaffolding, provider abstractions, Qdrant, basic API |
| 2 | Ingestion Pipeline | Sprints 3-4 | ✅ Complete | PDF parsing, chunking, enrichment, embedding, background jobs |
| 3 | Query Pipeline | Sprints 5-6 | ✅ Complete | Hybrid retrieval, reranking, corrective RAG, streaming |
| 4 | Frontend | Sprints 6-7 | ✅ Complete | Next.js app, chat UI, document management, settings |
| 4.5 | **Experiment Harness** | **Sprint 7** | ✅ **Complete** | **Opus 4.7 + extended thinking, document tags, token telemetry, batch ingest CLI, experiment runner CLI, judge LLM CLI** |
| 5 | Evaluation & Polish | Sprint 8 | Planned | RAGAS/DeepEval, Docker Compose hardening, observability, perf benchmarks |

Phase 4.5 was added in v1.1 of this document. It was not in the
original v1.0 plan; it expanded out of Sprint 7 to support the
RAG vs LLM Wiki experiment. See §4 Sprint 7 below for the as-built
breakdown and SRS §4.5 for the corresponding requirements.

---

## 2. Development Methodology

### 2.1 Approach

- **Backend-first**: The FastAPI backend is built and tested before the frontend, using OpenAPI docs and httpx for validation.
- **Provider-at-a-time**: Each provider abstraction (embedding, LLM, reranker) is implemented with one concrete provider first (the default), then additional providers are added as separate tasks.
- **Test alongside code**: Unit tests are written in the same sprint as the feature, not deferred. Integration tests follow once dependent components exist.
- **Vertical slices**: Each sprint delivers a working increment that can be tested end-to-end (via API or CLI), not just isolated modules.

### 2.2 Testing Strategy

| Layer | When Written | Runner | Coverage Target |
|---|---|---|---|
| Unit tests | Same sprint as feature | pytest | >= 80% per module |
| Integration tests | Sprint after dependencies land | pytest + fixtures | Key paths |
| API tests | Same sprint as route | pytest + httpx | All endpoints |
| Frontend tests | Same sprint as component | Vitest + RTL | Core interactions |
| E2E tests | Sprint 8 | Playwright | Critical user flows |
| RAG evaluation | Sprint 8 | RAGAS + DeepEval | Metric thresholds from SRS 9.1 |

---

## 3. Git Workflow

### 3.1 Branch Strategy

```
main                          ← production-ready, protected
  └── develop                 ← integration branch for sprint work
       ├── feat/S1-xxx        ← feature branches per task
       ├── fix/S2-xxx         ← bug fix branches
       └── chore/S1-xxx       ← tooling, config, infra
```

### 3.2 Branch Naming Convention

```
<type>/S<sprint>-<short-description>

Examples:
  feat/S1-fastapi-scaffold
  feat/S2-qdrant-hybrid-search
  fix/S3-chunker-token-count
  chore/S1-docker-compose
```

### 3.3 Merge Rules

- All merges to `develop` require a PR with passing CI (lint + tests).
- `develop` is merged to `main` at the end of each sprint (sprint release).
- Squash merges for feature branches; merge commits for `develop` → `main`.
- No direct commits to `main` or `develop`.

### 3.4 Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

Types: feat, fix, refactor, test, docs, chore, ci
Scopes: api, ingestion, query, providers, frontend, storage, config, eval
```

---

## 4. Sprint Plan

---

### Sprint 1: Project Scaffolding & Provider Abstractions

**Phase**: 1 — Foundation
**Goal**: Monorepo structure, FastAPI skeleton, provider interfaces, configuration system, and base infrastructure.

| ID | Task | SRS Refs | Acceptance Criteria |
|---|---|---|---|
| S1-01 | **Initialize monorepo structure** | Appendix C | `backend/` and `frontend/` directories exist. `pyproject.toml` with uv, `package.json` with pnpm. `.gitignore` updated. Old `app.py`, `utils/`, `requirements.txt` moved to `legacy/`. |
| S1-02 | **Set up backend tooling** | 6.10 | Ruff linting configured. pytest + pytest-asyncio configured. `uv run pytest` and `uv run ruff check` both pass on empty project. Pre-commit hooks installed. |
| S1-03 | **Implement configuration system** | Appendix B | Pydantic Settings model loads from `config.yaml` with env var overrides. All provider, ingestion, retrieval, and storage settings represented. Unit tests for config loading, defaults, and env overrides. |
| S1-04 | **FastAPI application scaffold** | 3.1, 8.1 | FastAPI app with router stubs for all 5 route groups (`/documents`, `/collections`, `/query`, `/conversations`, `/settings`). `/api/health` returns `200 OK`. CORS middleware configured. OpenAPI docs accessible at `/docs`. |
| S1-05 | **Define provider abstract interfaces** | NFR-4.1, Appendix A | `EmbeddingProvider`, `LLMProvider`, `RerankerProvider` ABCs defined in `providers/base.py`. `RerankResult`, `EmbeddingResult` dataclasses defined. Provider factory function that instantiates providers from config. Unit tests for factory. |
| S1-06 | **Implement OpenAI embedding provider** | FR-4.1, FR-4.3, FR-4.5, FR-4.6 | `OpenAIEmbeddingProvider` implements `EmbeddingProvider`. Supports `text-embedding-3-large` with configurable dimensions. Batch embedding with retry + exponential backoff. Unit tests with mocked API. |
| S1-07 | **Implement LiteLLM LLM provider** | FR-10.1, FR-10.2 | `LiteLLMProvider` implements `LLMProvider`. `generate()` and `generate_stream()` work for Anthropic, OpenAI, and Ollama model strings. Unit tests with mocked LiteLLM calls. |
| S1-08 | **Set up SQLAlchemy models and database** | 7.1 | SQLAlchemy 2.0 models for `collections`, `documents`, `conversations`, `messages`, `ingestion_jobs`. Alembic migration for initial schema. `database.py` with async session factory. SQLite default. Unit tests for model creation. |
| S1-09 | **Docker Compose skeleton** | 3.3 | `docker-compose.yml` with `backend` (Python 3.12), `qdrant` (latest), and `frontend` (Node 20 placeholder) services. `docker compose up` starts backend and Qdrant successfully. |
| S1-10 | **Structured logging setup** | FR-15.3 | JSON structured logging via `structlog`. Configurable verbosity via env var. Request ID middleware for FastAPI. All log calls use structured format. |

**Sprint 1 Deliverable**: `docker compose up` starts FastAPI + Qdrant. `/api/health` returns status. OpenAPI docs show all route stubs. Config loads from YAML/env. Provider interfaces defined with OpenAI embedding and LiteLLM providers working.

---

### Sprint 2: Qdrant Integration & Core API

**Phase**: 1 — Foundation
**Goal**: Qdrant vector storage with hybrid search, collections API, documents API, and basic query endpoint.

| ID | Task | SRS Refs | Acceptance Criteria |
|---|---|---|---|
| S2-01 | **Qdrant client wrapper** | FR-5.1, FR-5.2, FR-5.4 | `QdrantStore` class wraps `qdrant-client`. Creates collections with named dense (HNSW, 1024d) and sparse vectors. CRUD operations for points with full payload schema. Configurable connection URL. Unit tests with in-memory Qdrant. |
| S2-02 | **Qdrant hybrid search** | FR-7.1, FR-7.2, FR-7.3 | `QdrantStore.hybrid_search()` performs prefetch on both dense and sparse named vectors, fuses with RRF (configurable k). Returns ranked results with scores. Metadata filtering support (document_id, collection). Unit tests verify RRF ranking logic. |
| S2-03 | **Sparse vector generation** | FR-4.2 | BM25 sparse vector encoder using Qdrant's `FastEmbed` or `rank_bm25`. Tokenizes text, produces sparse index/value pairs. Integrated into storage pipeline. Unit tests. |
| S2-04 | **Collections API** | FR-5.3, 8.1 | `POST/GET/GET{id}/PUT/DELETE /api/collections` fully implemented. Creates corresponding Qdrant collection on POST. Cascading delete removes Qdrant collection + all documents. Pydantic request/response schemas. API tests with httpx. |
| S2-05 | **Documents API (upload & metadata)** | FR-1.6, FR-1.7, 8.1 | `POST /api/documents/upload` accepts multipart PDF upload, validates file type + size (NFR-3.2, NFR-3.3), saves to disk, creates document record with metadata (hash, size, page count via pypdf for now). `GET /api/documents` with collection/status filters. `GET /api/documents/{id}`. `DELETE /api/documents/{id}` removes file, DB record, and Qdrant points. API tests. |
| S2-06 | **Basic query endpoint** | 8.1, 8.2 | `POST /api/query` accepts query + collection_ids, embeds query via OpenAI provider, performs hybrid search on Qdrant, returns raw ranked chunks (no reranking or generation yet). Validates response schema matches SRS 8.2 structure. API tests. |
| S2-07 | **Health endpoint** | FR-15.1 | `/api/health` checks Qdrant connectivity, embedding provider reachability, LLM provider reachability. Returns structured status per dependency. |

**Sprint 2 Deliverable**: Full collections and documents CRUD via API. PDF upload stores file + metadata. Basic query returns hybrid-search results from Qdrant. Health endpoint reports dependency status.

---

### Sprint 3: Ingestion Pipeline — Parsing & Chunking

**Phase**: 2 — Ingestion Pipeline
**Goal**: Docling PDF parsing, document-aware chunking with parent-child relationships, background ingestion jobs.

| ID | Task | SRS Refs | Acceptance Criteria |
|---|---|---|---|
| S3-01 | **Docling PDF parser** | FR-1.1, FR-1.2, FR-1.3 | `DoclingParser` class wraps `docling.DocumentConverter`. Converts PDF to structured Markdown preserving headers, tables, lists, reading order. OCR enabled for scanned pages. Extracts document metadata (title, author, language). Unit tests with sample PDFs (text-heavy, table-heavy, scanned). |
| S3-02 | **PyMuPDF4LLM fallback parser** | FR-1.4 | `PyMuPDF4LLMParser` class wraps `pymupdf4llm`. Converts PDF to Markdown. Same interface as Docling parser. Unit tests. Performance benchmark vs Docling on same PDFs. |
| S3-03 | **Parser abstraction and factory** | NFR-4.1 | `DocumentParser` ABC with `parse(file_path) -> ParseResult` method. `ParseResult` contains markdown text, document metadata, and per-page data. Factory selects parser from config. Unit tests for factory. |
| S3-04 | **Document-aware chunker** | FR-2.1, FR-2.2, FR-2.3, FR-2.4 | `DocumentChunker` class. First pass: `MarkdownHeaderTextSplitter` splits on H1-H3 headers. Second pass: `RecursiveCharacterTextSplitter` with `tiktoken` token counting (512 tokens, 50 overlap) for oversized chunks. Each chunk carries metadata: header_chain, page_numbers, chunk_index. Unit tests verifying header preservation, token limits, overlap. |
| S3-05 | **Parent-child chunk relationships** | FR-2.5, FR-11.1 | Chunker produces two tiers: parent chunks (structural sections from header split) and child chunks (token-limited sub-chunks). Child chunks reference parent via `parent_chunk_id`. Both stored in Qdrant; children used for retrieval, parents available for context expansion. Unit tests verifying relationship integrity. |
| S3-06 | **Background ingestion orchestrator** | FR-1.7, FR-1.8 | `IngestionPipeline` class orchestrates: parse → chunk → embed → store. Runs as FastAPI background task. Updates `ingestion_jobs` and `documents` status at each stage. Atomic per document (failure rolls back Qdrant points). Re-ingestion deletes old points before inserting new. Integration test for full pipeline with small PDF. |
| S3-07 | **Wire upload to ingestion pipeline** | FR-1.7 | `POST /api/documents/upload` triggers background ingestion. `POST /api/documents/{id}/reingest` re-processes with optional new settings. `GET /api/documents/{id}` returns current ingestion status. API tests for async upload → poll status → complete flow. |

**Sprint 3 Deliverable**: Uploading a PDF triggers background ingestion: Docling parsing → document-aware chunking → embedding → Qdrant storage. Status trackable via API. Parent-child chunk hierarchy stored.

---

### Sprint 4: Ingestion Pipeline — Enrichment & Additional Providers

**Phase**: 2 — Ingestion Pipeline
**Goal**: Contextual enrichment, additional embedding providers, embedding model tracking.

| ID | Task | SRS Refs | Acceptance Criteria |
|---|---|---|---|
| S4-01 | **Contextual enrichment** | FR-3.1, FR-3.2, FR-3.3, FR-3.4 | `ContextualEnricher` class. For each chunk, calls LLM (via LLMProvider) to generate 1-3 sentence contextual summary describing the chunk's position and topic within the document. Summary prepended to chunk text before embedding. Cache summaries in DB keyed by chunk content hash. Configurable enable/disable. Unit tests with mocked LLM. |
| S4-02 | **Enrichment integration into pipeline** | FR-3.1 | `IngestionPipeline` includes enrichment step between chunking and embedding. `ingestion_jobs` status includes `enriching` state. Skipped when disabled in config. Integration test verifying enriched chunks have contextual prefix. |
| S4-03 | **Cohere embedding provider** | FR-4.4 | `CohereEmbeddingProvider` implements `EmbeddingProvider`. Supports `embed-v4` with configurable dimensions (Matryoshka). Batch embedding with retry. Unit tests with mocked API. |
| S4-04 | **Sentence-Transformers embedding provider** | FR-4.4 | `SentenceTransformersEmbeddingProvider` implements `EmbeddingProvider`. Loads model locally, runs inference on CPU/GPU. Supports any HuggingFace model string. Unit tests with small model. |
| S4-05 | **Ollama embedding provider** | FR-4.4 | `OllamaEmbeddingProvider` implements `EmbeddingProvider`. Calls local Ollama API. Unit tests with mocked HTTP. |
| S4-06 | **Embedding model tracking** | FR-4.7 | Each Qdrant point payload includes `embedding_model` field. Hybrid search filters to only match chunks with the currently configured embedding model. Warning logged if collection contains mixed models. Unit tests for filtering. |
| S4-07 | **Ingestion pipeline integration tests** | NFR-5.2 | End-to-end integration tests for the full ingestion pipeline: upload PDF → parse (Docling) → chunk (document-aware) → enrich (contextual) → embed (OpenAI) → store (Qdrant). Verify chunk count, metadata correctness, parent-child links, Qdrant point payloads. Test with 3 sample PDFs (text, tables, mixed). |

**Sprint 4 Deliverable**: Full ingestion pipeline with contextual enrichment. Multiple embedding providers available. Model tracking prevents cross-model contamination. Integration tests validate the complete pipeline.

---

### Sprint 5: Query Pipeline — Retrieval & Reranking

**Phase**: 3 — Query Pipeline
**Goal**: Multi-query expansion, dedicated reranking, parent-child context expansion.

| ID | Task | SRS Refs | Acceptance Criteria |
|---|---|---|---|
| S5-01 | **Multi-query expansion** | FR-6.1, FR-6.2 | `QueryExpander` class. Given a query, calls LLM to generate 2-3 alternative phrasings. Returns list of query strings. Configurable enable/disable. Unit tests with mocked LLM verifying diverse phrasings. |
| S5-02 | **Cohere reranker provider** | FR-8.1, FR-8.2 | `CohereRerankerProvider` implements `RerankerProvider`. Calls Cohere Rerank 3.5 API. Accepts query + list of document texts, returns `RerankResult` list with scores. Configurable top_k. Unit tests with mocked API. |
| S5-03 | **Cross-encoder reranker provider** | FR-8.3 | `CrossEncoderRerankerProvider` implements `RerankerProvider`. Uses `sentence-transformers` `CrossEncoder` with `BAAI/bge-reranker-v2-m3`. Runs locally. Unit tests with small model. |
| S5-04 | **Parent-child context expansion** | FR-11.1, FR-11.2, FR-11.3 | `ContextAssembler` class. Given retrieved child chunks, optionally fetches parent chunks from Qdrant. Modes: `off` (children only), `parent` (replace children with parents, deduplicated), `siblings` (children + adjacent chunks). Enforces token budget. Unit tests for each mode and budget enforcement. |
| S5-05 | **Query pipeline orchestrator** | FR-6, FR-7, FR-8, FR-11 | `QueryPipeline` class orchestrates: expand → hybrid search → rerank → assemble context. Configurable at each stage. Returns assembled context with metadata (scores, query variations, chunk provenance). Integration test with seeded Qdrant data. |
| S5-06 | **Multi-collection search** | FR-7.4, FR-7.5 | `QueryPipeline` accepts list of collection IDs. Searches across all specified Qdrant collections. Merges and reranks across collections. Metadata filtering by document, date range. Unit tests. |
| S5-07 | **Wire query API to pipeline** | 8.1, 8.2 | `POST /api/query` uses full `QueryPipeline`. Request schema accepts all options from SRS 8.2. Response includes answer placeholder (raw context for now) + sources + metadata. API tests validating full response shape. |

**Sprint 5 Deliverable**: Query API performs multi-query expansion → hybrid search across collections → reranking (Cohere or local) → context assembly with parent-child expansion. Returns ranked, assembled context with full metadata.

---

### Sprint 6: Query Pipeline — Generation & Streaming + Frontend Bootstrap

**Phase**: 3 (completion) + 4 (start) — Query Pipeline & Frontend
**Goal**: LLM answer generation with streaming, corrective RAG, conversations API. Bootstrap Next.js frontend.

| ID | Task | SRS Refs | Acceptance Criteria |
|---|---|---|---|
| S6-01 | **Answer generator** | FR-10.1, FR-10.4, FR-10.5, FR-10.6, FR-10.7 | `AnswerGenerator` class. Assembles context + query into prompt. Calls LLM via `LLMProvider.generate()`. System prompt instructs grounded answers only. Response includes source citations (document name, pages, header chain, score). Configurable system prompts. Unit tests with mocked LLM. |
| S6-02 | **Corrective RAG** | FR-9.1, FR-9.2, FR-9.3, FR-9.4, FR-9.5 | `RelevanceValidator` class. After reranking, calls LLM to score top chunks' relevance to query (0-1). If below threshold (configurable, default 0.5), reformulates query via LLM and triggers second retrieval pass. Max 2 attempts. If both fail, returns "insufficient context" message. Configurable enable/disable. Unit tests for both pass and fail paths. |
| S6-03 | **Integrate corrective RAG into query pipeline** | FR-9 | `QueryPipeline` includes validation step between reranking and generation. Metadata tracks `corrective_rag_triggered` and `retrieval_attempts`. Integration test with intentionally poor initial results triggering retry. |
| S6-04 | **WebSocket streaming endpoint** | FR-10.3, 8.1 | `WS /ws/query` accepts query message, streams answer tokens in real-time via `LLMProvider.generate_stream()`. Sends final message with sources and metadata after stream completes. Connection lifecycle management (open, message, close, error). Integration test with WebSocket client. |
| S6-05 | **Conversations API** | 8.1, FR-13.5, FR-13.7 | `POST/GET/GET{id}/DELETE /api/conversations` fully implemented. Messages stored with role, content, sources JSON. `POST /api/query` with `conversation_id` appends previous Q&A as context. API tests. |
| S6-06 | **Next.js project scaffold** | 6.2 | `frontend/` initialized with Next.js 15 (App Router), TypeScript, Tailwind CSS, pnpm. shadcn/ui installed and configured. App layout with sidebar navigation (Chat, Documents, Collections, Settings). Zustand store skeleton. TanStack Query provider. `pnpm dev` serves at localhost:3000. |
| S6-07 | **API client and types** | 6.2 | `frontend/src/lib/api.ts` — typed fetch wrapper for all backend REST endpoints. `frontend/src/lib/websocket.ts` — WebSocket client with reconnect logic. TypeScript types generated from or mirroring backend Pydantic schemas. |

**Sprint 6 Deliverable**: Full query pipeline with generation, streaming, and corrective RAG. Conversations API stores chat history. Next.js frontend scaffolded with API client ready.

---

### Sprint 7: Experiment Harness + Frontend (As-built)

**Phase**: 4 (Frontend) + 4.5 (Experiment Harness)
**Status**: ✅ Complete (2026-05-04)
**Goal**: Make the system experiment-ready for the RAG vs LLM Wiki
comparison: backend supports Opus 4.7 with extended thinking, document
tags, and token telemetry; CLIs drive batch ingestion and a fixed
question set; frontend exposes the full chat / documents /
collections / settings surface; a judge CLI scores both runs against a
shared rubric.

Shipped in four sequential pull requests. Each PR was independently
reviewable, tested, and merged in order.

#### PR-A: Backend foundations — `feat/S7-experiment-backend`

| ID | Task | SRS Refs | Acceptance |
|---|---|---|---|
| S7-A1 | **Default model + extended thinking** | FR-19 | `LLM_MODEL` default → `claude-opus-4-7`. New `REASONING_EFFORT` setting maps `off/low/medium/high/xhigh` → `0/4096/8192/16384/32000` budget tokens via `providers/llm/thinking.py`. `AnswerGenerator` forces `temperature=1.0` whenever thinking is enabled (Anthropic requirement); previous hardcoded `temperature=0.2` removed. Streaming asks LiteLLM for `include_usage` so the final chunk carries token counts. |
| S7-A2 | **Separate enrichment model** | FR-19.4 | New `ENRICHMENT_LLM_MODEL` setting (default `claude-sonnet-4-5-20250929`). New `create_enrichment_llm_provider(settings)` factory used by the ingestion pipeline so per-chunk summarization runs on a cheaper model than answer generation. |
| S7-A3 | **Document tags column** | FR-16 | `Document.tags` JSON column added via idempotent `init_db()` `ALTER TABLE` upgrade (no Alembic in project today). Upload route accepts optional `tags_json` multipart form field, validated as JSON object. `DocumentResponse` exposes `tags`. |
| S7-A4 | **Token telemetry + ingestion timing** | FR-17, FR-18 | `Message` model gains `model_used`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `thinking_tokens` columns. `LiteLLMProvider.last_usage` captures Anthropic `reasoning_tokens` as `thinking_tokens`. `/query` and WebSocket emit usage in metadata. `DocumentResponse` joins the latest `IngestionJob` to expose `ingestion_started_at`, `ingestion_completed_at`, `ingestion_seconds`. |
| S7-A5 | **Tests** | NFR-5.1 | 22 new unit tests covering thinking helper mapping, generator thinking/temperature behavior, LiteLLM usage extraction (including Anthropic `reasoning_tokens`), document tags round-trip, ingestion-timing projection, and idempotent in-place schema upgrade. Full unit suite: 109 → 109 pass. |

**PR-A deliverable:** Backend can be configured for the experiment.
The schema migrations are non-destructive on existing dev DBs.

#### PR-B: Batch ingestion + experiment runner CLIs — `feat/S7-experiment-runner`

| ID | Task | SRS Refs | Acceptance |
|---|---|---|---|
| S7-B1 | **Corpus manifest** | FR-20 | `experiments/corpus.yaml` populated with the 24-paper schema (3 collections × 8 documents) and per-document `tags` (domain, role, year, authors, title). Role values include compound roles (`Chrono/Anchor`) that the role-sort handles correctly. |
| S7-B2 | **Question set** | FR-21 | `experiments/questions.yaml` with 13 questions: 10 across five Wiki-leaning tiers (chronological, conflict, multi-hop, emergence, policy) plus 3 RAG-favoring point-source bias-checks. Each question has `id`, `tier`, `bias`, `collections`, `text`. |
| S7-B3 | **Ingest CLI** | FR-20 | `backend/scripts/ingest_corpus.py` reads `corpus.yaml`, ensures collections via `POST /collections`, sorts by `ingest_order`, uploads with `tags_json`, polls each document to terminal status, writes `experiments/results/ingest-<ts>.json` with per-document timings and per-domain totals. Flags: `--dry-run`, `--only`, `--skip-completed`, `--poll-interval`, `--poll-timeout`. |
| S7-B4 | **Experiment runner CLI** | FR-21 | `backend/scripts/run_experiment.py` reads `questions.yaml`, submits each question in a fresh conversation via `POST /query` with configurable `reasoning_effort`, writes `experiments/results/run-<ts>.json` with answers + sources + metadata. Flags: `--reasoning-effort`, `--repeat`, `--collections`, `--only-tier`, `--only-id`, `--dry-run`. |
| S7-B5 | **Console entry points** | FR-20, FR-21 | `pyproject.toml [project.scripts]` registers `rag2compare-ingest` and `rag2compare-run`. Wheel includes the `scripts/` package. |
| S7-B6 | **Tests** | NFR-5.1 | 28 new unit tests covering manifest parsing, role sort key (including compound roles), upload payload formation, question filtering, query payload shape, dry-run behavior. Full unit suite: 109 → 137 pass. |

**PR-B deliverable:** End-to-end experiment ingestion + querying runs
from CLI, no UI required.

#### PR-C: Frontend pull-forward — `feat/S7-frontend-ui`

| ID | Task | SRS Refs | Acceptance |
|---|---|---|---|
| S7-C1 | **UI primitive components** | 6.2 | `components/ui/{button,card,input,label,textarea,select,badge,skeleton,separator,modal}.tsx` hand-written so the project doesn't require running the `shadcn` CLI (no network at install time). Modal uses the native `<dialog>` element to avoid pulling in `@radix-ui/react-dialog`. |
| S7-C2 | **Chat page** | FR-13.1–13.7, FR-19 | `app/page.tsx`: collection multi-select chips, reasoning-effort dropdown (defaults to server's `reasoning_effort`), WebSocket streaming, per-turn metadata badges (`latency_ms`, `prompt/completion/thinking tokens`, `retrieval_count → reranked_count`), expandable source cards with verbatim chunk text + page numbers + relevance scores. Cmd/Ctrl+Enter to submit. |
| S7-C3 | **Documents page** | FR-12, FR-16, FR-17 | `app/documents/page.tsx`: collection picker, multi-file upload form with role/domain/year/authors fields serialized to `tags_json`, status-aware table showing role tag, ingestion seconds, chunk count, file size; reingest + delete actions. Auto-polls every 2s while any document is mid-pipeline (status not terminal). |
| S7-C4 | **Collections page** | FR-12.4 | `app/collections/page.tsx`: list cards with document counts and timestamps, create / edit / delete via confirmation modals. |
| S7-C5 | **Settings page** | FR-14, FR-19 | `app/settings/page.tsx`: read-only display of `GET /api/settings` (LLM model, reasoning effort, embedding/reranker, top-k, hybrid search), with health-cell status from `/api/health` (auto-refresh every 15s). |
| S7-C6 | **Data hooks** | NFR-4.2 | `hooks/use-{collections,documents,settings,stream-query}.ts` — TanStack Query for fetches and mutations, custom hook abstracting the `QueryWebSocket` lifecycle for chat. WebSocket URL derives from `window.location` so the same build works in local dev and behind a proxy. |
| S7-C7 | **Type + API client updates** | NFR-4.2 | `lib/types.ts` mirrors PR-A backend additions (`tags`, `ingestion_seconds`, `reasoning_effort`, token-count fields, `"usage"` WS event). `lib/api.ts` gains `uploadDocuments(files, tags)`. `lib/websocket.ts` handles the new `usage` event. |
| S7-C8 | **Build verification** | NFR-5.1 | `pnpm build` produces 5 static routes with no type errors. `pnpm lint` clean. |

**PR-C deliverable:** All four nav pages functional — placeholders
removed.

#### PR-D: Judge LLM tooling — `feat/S7-judge-tooling`

| ID | Task | SRS Refs | Acceptance |
|---|---|---|---|
| S7-D1 | **Rubric** | FR-22.3 | `experiments/rubric.yaml` with four criteria (Groundedness, Structural Integrity, Conflict Awareness, Inter-Paper Mapping), each with anchored 1/5/10 definitions. |
| S7-D2 | **Judge CLI** | FR-22 | `backend/scripts/judge_runs.py` pairs runs by question id, blinds answers as System A/B with seeded RNG (mapping recorded for un-blinding), submits to LiteLLM with `response_format=json_object`, parses defensively (extracts first balanced `{...}`, coerces ints to 1-10 range, flags missing scores), aggregates per-system × per-criterion × per-tier means. Default judge: `gpt-5` (cross-family). |
| S7-D3 | **Inter-rater reliability** | FR-22.6 | `--secondary-judge MODEL --secondary-judge-questions <ids>` re-judges a subset with a different model. Output's `secondary.agreement.max_deltas` field reports per-criterion worst delta between the two judges. |
| S7-D4 | **Resume support** | FR-22.7 | `--resume <prior-judged-file>` skips question_ids already scored by the same judge model. Long judge runs (~5–10 min) are expensive enough to warrant idempotent resumption. |
| S7-D5 | **Console entry point + docs** | FR-22 | `pyproject.toml` registers `rag2compare-judge`. `experiments/README.md` gains a Step 3 section documenting workflow, Wiki run schema requirement, inter-rater reliability spot-check, output schema, and how each hypothesis maps to a `judged-*.json` check. |
| S7-D6 | **Tests** | NFR-5.1 | 36 new unit tests covering rubric parsing, blinding determinism + balance, prompt assembly (system order, anchors, sources, empty handling), JSON-from-prose extraction, score coercion edge cases, aggregation + tier breakdowns, inter-rater delta math, dry-run behavior. Full unit suite: 137 → 173 pass. |

**PR-D deliverable:** Closed loop on the experiment — given both
runs, a judge produces a scored comparison artifact.

#### Sprint 7 Deliverable Summary

- Backend ready for Opus 4.7 + xhigh thinking with full token telemetry
- 24-paper corpus manifest + 13-question evaluation set + 4-criterion judge rubric
- Three CLIs: `rag2compare-ingest`, `rag2compare-run`, `rag2compare-judge`
- Functional UI for chat, documents, collections, settings
- 173 backend unit tests pass
- Frontend `pnpm build` and `pnpm lint` clean
- Workflow documented in `experiments/README.md` + `docs/RUNBOOK.md`

#### Items deferred to Sprint 8

- **Frontend tests** (S7-08 in v1.0 plan): Vitest + RTL was deferred — the four pages are exercised manually plus by the Next.js static type/lint pipeline. Belongs to Sprint 8 alongside RAGAS evaluation.
- **Persisted UI settings** (`PUT /api/settings`): backend stub returns current settings; full mutation handling deferred.
- **Vision-based parser** (FR-1.5): Sprint 8 task; Docling + PyMuPDF4LLM cover the experiment corpus.

---

### Sprint 8: Evaluation, Polish & Deployment

**Phase**: 5 — Evaluation & Polish
**Status**: Planned
**Goal**: RAG evaluation suite (RAGAS/DeepEval), frontend test setup,
E2E tests, vision parsing, Docker Compose production hardening,
performance benchmarking. Picks up the items deferred from Sprint 7
(see Sprint 7 §"Items deferred to Sprint 8").

| ID | Task | SRS Refs | Acceptance Criteria |
|---|---|---|---|
| S8-01 | **Curate evaluation dataset** | 9.1 | `tests/eval/dataset.json` with >= 50 Q&A pairs across >= 5 sample PDFs. Covers: factual recall (20), table lookups (10), multi-document synthesis (10), unanswerable questions (10). Ground-truth answers and relevant chunks annotated. |
| S8-02 | **RAGAS evaluation suite** | 9.1 | `tests/eval/test_rag_quality.py` runs RAGAS evaluation against the live pipeline. Measures faithfulness, answer relevancy, context precision, context recall. Results printed as table and saved to JSON. Configurable LLM judge. |
| S8-03 | **DeepEval CI quality gates** | 9.1 | DeepEval test cases wrapping the same eval dataset. Threshold enforcement: faithfulness >= 0.85, answer relevancy >= 0.80. Runs via `pytest tests/eval/`. Designed for CI integration. |
| S8-04 | **Vision-based PDF parser** | FR-1.5 | `VisionParser` class. Renders PDF pages to images (via PyMuPDF). Sends images to multimodal LLM (via LLMProvider) with prompt to extract Markdown. Same `DocumentParser` interface. Configurable pages-per-batch. Unit tests with mocked LLM. |
| S8-05 | **E2E tests** | NFR-5.2 | Playwright tests for critical user flows: (1) Upload PDF → verify appears in library with "complete" status. (2) Ask question → verify streaming answer with source citations. (3) Create collection → upload to it → query against it. (4) Change settings → verify persistence. |
| S8-06 | **Docker Compose production config** | 3.3 | Production `docker-compose.yml` with: backend (gunicorn + uvicorn workers), frontend (Next.js standalone build), Qdrant (persistent volume), optional Ollama. Environment file template (`.env.example`). Health check configs. `docker compose up` starts full stack. |
| S8-07 | **Query logging and observability** | FR-15.2, FR-15.3 | All query pipeline stages log structured events: query text, expansion results, retrieval count, reranking scores, corrective RAG triggers, generation model/latency. Latency tracked per stage. Cost estimation per query (token counts × price). Logs queryable via structured JSON. |
| S8-08 | **Performance validation** | NFR-1.1 - NFR-1.4 | Benchmark script measuring: query-to-first-token latency (target < 3s), full pipeline latency (target < 10s p95), ingestion throughput (target >= 10 pages/sec). Run against corpus of 50 PDFs. Results documented. Bottlenecks identified and filed as issues. |
| S8-09 | **Project documentation** | — | Updated `README.md` with: architecture overview, quickstart (Docker Compose), development setup, configuration reference, API reference link (OpenAPI docs). `docs/ARCHITECTURE.md` with system diagrams. `CONTRIBUTING.md` with branch naming, commit convention, test instructions. |

**Sprint 8 Deliverable**: RAG quality validated against thresholds. E2E tests passing. Full Docker Compose deployment working. Vision parser available. Performance benchmarked. Project documented.

---

## 5. Dependency Graph

The following shows the critical-path dependencies between tasks. Tasks not listed have no blockers beyond their sprint's prior tasks.

```
S1-03 (config) ──────────────┬──► S1-05 (provider interfaces)
                             │
                             ├──► S1-06 (OpenAI embedding)
                             │
                             └──► S1-07 (LiteLLM provider)

S1-05 (provider interfaces) ─┬──► S1-06 (OpenAI embedding)
                             ├──► S1-07 (LiteLLM provider)
                             ├──► S4-03 (Cohere embedding)
                             ├──► S4-04 (SentenceTransformers)
                             ├──► S4-05 (Ollama embedding)
                             ├──► S5-02 (Cohere reranker)
                             └──► S5-03 (Cross-encoder reranker)

S1-04 (FastAPI scaffold) ────┬──► S2-04 (Collections API)
                             ├──► S2-05 (Documents API)
                             └──► S2-06 (Query API)

S1-06 (OpenAI embedding) ────┬──► S2-01 (Qdrant wrapper)
                             └──► S2-03 (Sparse vectors)

S1-08 (SQLAlchemy models) ───┬──► S2-04 (Collections API)
                             ├──► S2-05 (Documents API)
                             └──► S6-05 (Conversations API)

S2-01 (Qdrant wrapper) ──────┬──► S2-02 (Hybrid search)
                             └──► S3-06 (Ingestion orchestrator)

S2-02 (Hybrid search) ───────┬──► S2-06 (Query API)
                             └──► S5-05 (Query pipeline)

S3-01 (Docling parser) ──────┬──► S3-04 (Chunker)
                             └──► S3-06 (Ingestion orchestrator)

S3-04 (Chunker) ─────────────┬──► S3-05 (Parent-child)
                             └──► S3-06 (Ingestion orchestrator)

S3-06 (Ingestion pipeline) ──┬──► S3-07 (Wire upload)
                             ├──► S4-01 (Contextual enrichment)
                             └──► S4-07 (Integration tests)

S5-01 (Multi-query) ─────────┤
S5-02 (Cohere reranker) ─────┤
S5-04 (Context expansion) ───┼──► S5-05 (Query pipeline)
S2-02 (Hybrid search) ───────┘

S5-05 (Query pipeline) ──────┬──► S5-07 (Wire query API)
                             ├──► S6-01 (Answer generator)
                             ├──► S6-02 (Corrective RAG)
                             └──► S6-04 (WebSocket streaming)

S6-06 (Next.js scaffold) ────┬──► S6-07 (API client)
                             └──► S7-01 through S7-07 (all frontend tasks)

S6-07 (API client) ──────────┬──► S7-01 (Chat interface)
                             ├──► S7-04 (Document upload)
                             └──► S7-06 (Collection management)
```

### Critical Path

The longest dependency chain determining minimum project duration:

```
S1-03 → S1-05 → S1-06 → S2-01 → S2-02 → S3-06 → S5-05 → S6-01 → S6-04 → S7-01
config   ABCs    embed   qdrant  hybrid  ingest   query   gen     stream   chat UI
                                 search  pipeline pipeline
```

This chain spans Sprints 1-7 and represents the core data flow from configuration through to the user-facing chat experience. All other work runs in parallel with this chain.

---

## 6. Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Docling parsing quality insufficient for complex PDFs** | Medium | High | PyMuPDF4LLM fallback parser ready from Sprint 3. Vision parser available as escape hatch in Sprint 8. Evaluate Docling against 10 real-world PDFs before committing. |
| R2 | **Qdrant sparse vector / hybrid search API changes** | Low | Medium | Pin `qdrant-client` version. Wrap all Qdrant calls in `QdrantStore` abstraction. Integration tests catch breaking changes. |
| R3 | **LiteLLM compatibility issues with some providers** | Medium | Medium | LiteLLM provider is one implementation of the `LLMProvider` interface. Direct Anthropic/OpenAI providers can be added as fallbacks without architectural changes. |
| R4 | **Contextual enrichment cost explosion on large documents** | Medium | Medium | Enrichment is configurable (disable by default for large documents). Cache summaries to avoid re-computation. Use fast/cheap model (Haiku-class) for enrichment. Monitor token usage per ingestion job. |
| R5 | **WebSocket streaming reliability** | Low | Medium | Implement reconnection logic in frontend client. Fall back to non-streaming `POST /api/query` if WebSocket fails. Heartbeat/ping-pong to detect stale connections. |
| R6 | **Frontend/backend schema drift** | Medium | Low | Generate TypeScript types from backend Pydantic schemas (or maintain shared type definitions). API tests validate response shapes. |
| R7 | **RAG evaluation metrics don't meet thresholds** | Medium | High | Thresholds are tunable. Evaluation identifies which pipeline stage is the bottleneck (retrieval vs generation). Iterate on prompts, chunking strategy, or reranking before adjusting thresholds. |
| R8 | **Docker Compose resource constraints on local machines** | Medium | Medium | Document minimum hardware requirements. Qdrant and Ollama are memory-hungry — provide guidance for non-GPU machines. Ollama is optional. |
| R9 | **Same-family judge bias inflates Wiki scores** | Medium | High | Default judge is cross-family (`gpt-5` when answer model is Claude). Inter-rater reliability spot-check via `--secondary-judge gemini-2.5-pro` flags calibration drift. Decision rule: if any criterion's max-delta > 2, fall back to mean-of-judges or add a third judge. Documented in [`docs/RUNBOOK.md`](./RUNBOOK.md) §3.2. |
| R10 | **Asymmetric ingestion-cost confounds H3** | Medium | Medium | RAG side uses Sonnet 4.5 for per-chunk enrichment; Wiki side uses Opus 4.7 for full ingestion. This *is* the experiment's hypothesis (Wiki pays compilation tax upfront), but readers must understand it isn't apples-to-apples on raw cost. Writeup must explicitly call out the model choice on each side. To eliminate the asymmetry, set `ENRICHMENT_LLM_MODEL=claude-opus-4-7` and re-run. |
| R11 | **Anthropic extended-thinking budget cap shifts** | Low | Low | The `xhigh` budget (32K tokens) is hardcoded in `providers/llm/thinking.py`. If Anthropic raises or lowers the API cap, the value can be changed in one place. Older runs remain reproducible because `metadata.reasoning_effort` and `metadata.thinking_tokens` are persisted per query. |

---

## 7. Definition of Done

A task is "done" when all of the following are met:

### Code
- [ ] Implementation complete and handles edge cases
- [ ] No regressions in existing tests (`pytest` passes, `ruff check` clean)
- [ ] New unit tests written with >= 80% coverage for new code
- [ ] Integration tests written where the task involves cross-component interaction
- [ ] Code follows project conventions (Conventional Commits, structured logging, type hints)

### Review
- [ ] PR submitted to `develop` with description linking to task ID
- [ ] CI pipeline passes (lint, type check, tests)
- [ ] PR reviewed and approved (or self-reviewed for solo development)

### Documentation
- [ ] Public API changes reflected in Pydantic schemas (auto-documented via OpenAPI)
- [ ] Complex logic has inline comments explaining "why", not "what"
- [ ] Config changes documented in `.env.example` or `config.yaml`

---

*End of SDP document.*
