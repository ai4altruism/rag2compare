# System Requirements Specification (SRS)

## Rag2Compare v2.0

| Field | Value |
|---|---|
| **Document Version** | 1.2 |
| **Date** | 2026-05-04 |
| **Status** | As-built (Sprint 7 complete) |
| **Project** | rag2compare |
| **Revision history** | 1.0 (2026-03-20) Draft · 1.1 (2026-05-04) Adds §4.5 Experiment Harness, §9.3 Experiment Evaluation; updates §6 to Opus 4.7 default; updates §7.1 schema and §8.2 response shape for as-built fields. · 1.2 (2026-05-04) Rewrites FR-19 from manual `{type: enabled, budget_tokens}` to adaptive thinking — Opus 4.7 rejects manual mode with 400; adds `max` tier and `output_config={effort}` parameter; documents `display` default flip to `omitted` on Opus 4.7. |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Overview](#2-system-overview)
3. [Architecture](#3-architecture)
4. [Functional Requirements](#4-functional-requirements)
   - 4.1 Document Ingestion
   - 4.2 Query Pipeline
   - 4.3 Frontend
   - 4.4 System Administration
   - **4.5 Experiment Harness** _(added in v1.1)_
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [Technology Selections](#6-technology-selections)
7. [Data Model](#7-data-model)
8. [API Specification](#8-api-specification)
9. [Evaluation & Quality Assurance](#9-evaluation--quality-assurance)
   - 9.1 RAG Evaluation Framework
   - 9.2 Testing Strategy
   - **9.3 Experiment Evaluation: RAG vs LLM Wiki** _(added in v1.1)_
10. [Migration Strategy](#10-migration-strategy)
11. [Appendices](#11-appendices)

---

## 1. Introduction

### 1.1 Purpose

This document specifies the requirements for a comprehensive rewrite of the rag2compare project, upgrading it from a Streamlit-based prototype to a production-grade, general-purpose Retrieval-Augmented Generation (RAG) system with a React/Next.js frontend and FastAPI backend.

### 1.2 Scope

The system enables users to upload PDF documents (and potentially other document types), process them into searchable embeddings, and query them using natural language with LLM-generated answers grounded in the source material. It must handle text-heavy documents, structured tables, charts/diagrams, and scanned pages.

### 1.3 Design Principles

- **Provider-agnostic**: All LLM, embedding, and reranking providers are swappable via configuration. No hard dependency on any single vendor.
- **Local-first deployment**: The entire system runs self-hosted. Cloud APIs are used for embeddings/LLM calls but no managed SaaS infrastructure is required for storage or compute.
- **Offline-capable where practical**: Embedding and LLM layers support local model alternatives (Ollama, sentence-transformers) even though online operation is the default.
- **Evaluate before optimizing**: Every retrieval and generation improvement must be measurable against a baseline.

### 1.4 Target Scale

| Dimension | Target |
|---|---|
| Document corpus | 100 - 1,000 PDFs |
| Document size | 1 - 500+ pages per PDF |
| Concurrent users | 1 - 20 |
| Query latency (p95) | < 5 seconds end-to-end |
| Ingestion throughput | ~10 pages/second sustained |

### 1.5 Definitions

| Term | Definition |
|---|---|
| **Chunk** | A segment of a document, with metadata, stored as an embedding vector |
| **Dense retrieval** | Semantic similarity search using embedding vectors |
| **Sparse retrieval** | Keyword-based search (BM25) |
| **Hybrid search** | Combination of dense and sparse retrieval, fused via RRF |
| **RRF** | Reciprocal Rank Fusion — algorithm that merges ranked lists from multiple retrievers |
| **Reranking** | A second-pass scoring of retrieved chunks using a cross-encoder or dedicated reranker model |
| **Contextual retrieval** | Prepending document-level context to each chunk before embedding |
| **Corrective RAG** | Post-retrieval validation that reformulates queries when initial results are poor |

---

## 2. System Overview

### 2.1 Current System (v1.0)

The existing application is a single-process Streamlit app with the following pipeline:

```
PDF upload → pypdf extraction → RecursiveCharacterTextSplitter (1000 chars) →
OpenAI text-embedding-3-small → ChromaDB → cosine similarity (top-10) →
LLM-based reranking (top-3) → LLM answer generation → Streamlit chat UI
```

**Key limitations:**
- pypdf loses all document structure (tables, headers, layout)
- Character-based chunking ignores document semantics
- No hybrid search (dense-only retrieval)
- LLM-based reranking is slow, expensive, and unreliable
- No evaluation framework to measure quality
- Streamlit UI is not suitable for production use
- Tightly coupled — no API layer for integration

### 2.2 Target System (v2.0)

```
Document upload → Docling AI parsing (Markdown) → Document-aware chunking →
Contextual enrichment → Dual embedding (dense + sparse) →
Qdrant hybrid search → Dedicated reranking → Corrective RAG loop →
LLM answer generation → React/Next.js UI
```

All served behind a FastAPI backend with a clean REST API.

---

## 3. Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js + React)                      │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ Document  │  │    Chat      │  │ Collection│  │  Settings /  │  │
│  │ Upload &  │  │  Interface   │  │  Manager  │  │  Provider    │  │
│  │ Status    │  │  + Sources   │  │           │  │  Config      │  │
│  └──────────┘  └──────────────┘  └───────────┘  └──────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ REST API (HTTP/JSON)
                             │ WebSocket (streaming responses)
┌────────────────────────────┴────────────────────────────────────────┐
│                      BACKEND (FastAPI + Python)                     │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     API Layer (FastAPI)                       │   │
│  │  /documents  /collections  /query  /settings  /health        │   │
│  └──────────┬──────────────────────────┬────────────────────────┘   │
│             │                          │                            │
│  ┌──────────▼──────────┐    ┌──────────▼──────────────────────┐    │
│  │  Ingestion Pipeline  │    │     Query Pipeline              │    │
│  │                      │    │                                 │    │
│  │  1. PDF Parsing      │    │  1. Query Expansion             │    │
│  │     (Docling)        │    │     (multi-query)               │    │
│  │  2. Chunking         │    │  2. Hybrid Retrieval            │    │
│  │     (doc-aware)      │    │     (dense + BM25)              │    │
│  │  3. Contextual       │    │  3. Reranking                   │    │
│  │     Enrichment       │    │     (Cohere / cross-encoder)    │    │
│  │  4. Embedding        │    │  4. Relevance Validation        │    │
│  │     (dense + sparse) │    │     (corrective RAG)            │    │
│  │  5. Storage          │    │  5. Answer Generation           │    │
│  │     (Qdrant)         │    │     (streaming)                 │    │
│  └──────────────────────┘    └─────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   Provider Abstraction Layer                  │   │
│  │                                                               │   │
│  │  EmbeddingProvider    LLMProvider       RerankerProvider      │   │
│  │  ├─ OpenAI            ├─ Anthropic      ├─ Cohere Rerank     │   │
│  │  ├─ Cohere            ├─ OpenAI         ├─ Cross-encoder     │   │
│  │  ├─ Jina              ├─ Ollama         └─ (local models)    │   │
│  │  ├─ Sentence-         ├─ vLLM                                │   │
│  │  │  Transformers      └─ LiteLLM                             │   │
│  │  └─ Ollama               (router)                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Qdrant          │  │   SQLite /   │  │   Background Task   │  │
│  │   (vectors +      │  │   PostgreSQL │  │   Queue (asyncio /  │  │
│  │    sparse index)  │  │   (metadata) │  │    Celery)          │  │
│  └──────────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Responsibilities

| Component | Responsibility |
|---|---|
| **Next.js Frontend** | Document upload, chat UI with streaming, collection management, source citation display, provider configuration |
| **FastAPI Backend** | REST API, WebSocket streaming, request validation, orchestration |
| **Ingestion Pipeline** | PDF parsing, chunking, contextual enrichment, embedding, vector storage |
| **Query Pipeline** | Query expansion, hybrid retrieval, reranking, relevance validation, answer generation |
| **Provider Abstraction** | Unified interfaces for LLM, embedding, and reranker providers — swappable via config |
| **Qdrant** | Vector storage, dense + sparse indexing, hybrid search with RRF |
| **Metadata DB** | Document metadata, collections, processing status, user settings (SQLite default, PostgreSQL optional) |
| **Task Queue** | Async document ingestion, batch operations |

### 3.3 Deployment Topology

All components run locally via Docker Compose:

```yaml
services:
  frontend:    # Next.js (Node 20)
  backend:     # FastAPI (Python 3.12)
  qdrant:      # Qdrant vector DB
  # Optional:
  ollama:      # Local LLM serving
```

---

## 4. Functional Requirements

### 4.1 Document Ingestion

#### FR-1: PDF Parsing

| ID | Requirement |
|---|---|
| FR-1.1 | The system SHALL parse PDF documents using Docling (IBM) as the primary parser, producing structured Markdown output preserving headers, paragraphs, tables, lists, and reading order. |
| FR-1.2 | The system SHALL support OCR for scanned PDF pages via Docling's integrated Tesseract/EasyOCR support. |
| FR-1.3 | The system SHALL extract tables into Markdown table format, preserving row/column structure. |
| FR-1.4 | The system SHALL provide a fallback parser (PyMuPDF4LLM) for fast bulk processing when document structure preservation is not critical. |
| FR-1.5 | The system SHALL support vision-based parsing as an optional mode, using a multimodal LLM (e.g., Claude, GPT-4o) to interpret page screenshots for documents with complex charts, diagrams, or non-standard layouts. |
| FR-1.6 | The system SHALL extract and store document-level metadata: title, author, page count, creation date, file size, and detected language. |
| FR-1.7 | The system SHALL track ingestion status per document: queued, parsing, chunking, embedding, complete, failed. |
| FR-1.8 | The system SHALL support re-ingestion of previously processed documents (e.g., after parser upgrade) without duplicating entries. |

#### FR-2: Chunking

| ID | Requirement |
|---|---|
| FR-2.1 | The system SHALL use document-aware chunking via `MarkdownHeaderTextSplitter` as the primary strategy, splitting on document structure (headers H1-H3) when Markdown output is available. |
| FR-2.2 | The system SHALL apply a secondary `RecursiveCharacterTextSplitter` pass to break oversized structural chunks into token-limited segments (target: 512 tokens, 50-token overlap). |
| FR-2.3 | The system SHALL use token-based sizing (via `tiktoken`) rather than character-based sizing. |
| FR-2.4 | The system SHALL preserve chunk hierarchy metadata: parent section title, header chain (e.g., "Chapter 3 > Section 3.2 > Subsection 3.2.1"), source page number(s), and position within document. |
| FR-2.5 | The system SHALL store parent-child relationships between chunks: small chunks (children) are used for retrieval, and their enclosing section (parent) is available for expanded context delivery to the LLM. |

#### FR-3: Contextual Enrichment

| ID | Requirement |
|---|---|
| FR-3.1 | The system SHALL prepend a contextual summary to each chunk before embedding, generated by an LLM. The summary SHALL describe where the chunk fits within the overall document (section, topic, relationship to surrounding content). |
| FR-3.2 | The contextual summary SHALL be 1-3 sentences and follow this format: `"This chunk is from [section/location] of [document title], discussing [topic]. [Additional context about what precedes/follows this chunk.]"` |
| FR-3.3 | The system SHALL cache contextual summaries so they are not regenerated on re-embedding with the same parser output. |
| FR-3.4 | Contextual enrichment SHALL be configurable (enable/disable) since it adds LLM cost per chunk during ingestion. |

#### FR-4: Embedding

| ID | Requirement |
|---|---|
| FR-4.1 | The system SHALL generate dense vector embeddings for each chunk using a configurable embedding provider. |
| FR-4.2 | The system SHALL generate sparse vectors (BM25 term frequencies) for each chunk to support hybrid search. |
| FR-4.3 | The default embedding provider SHALL be OpenAI `text-embedding-3-large` at 1024 dimensions. |
| FR-4.4 | The system SHALL support the following embedding providers via a common interface: OpenAI, Cohere, Jina, Sentence-Transformers (local), and Ollama (local). |
| FR-4.5 | The system SHALL support Matryoshka dimension reduction for providers that offer it (OpenAI, Cohere, Jina), configurable via settings. |
| FR-4.6 | The system SHALL process embeddings in configurable batches with retry logic and exponential backoff. |
| FR-4.7 | The system SHALL track embedding model identity per chunk so that chunks embedded with different models are not mixed in search results. |

#### FR-5: Storage

| ID | Requirement |
|---|---|
| FR-5.1 | The system SHALL store all vectors in Qdrant, running locally via Docker. |
| FR-5.2 | Each Qdrant collection SHALL contain both dense vectors (HNSW index) and sparse vectors (sparse index) for the same chunks. |
| FR-5.3 | The system SHALL support multiple named collections, allowing users to organize documents into separate searchable groups. |
| FR-5.4 | The system SHALL store the following metadata per chunk in Qdrant payload: source document ID, filename, page number(s), header chain, chunk index, chunk token count, contextual summary (if generated), and embedding model identifier. |
| FR-5.5 | Document-level metadata (title, author, status, upload date, file hash) SHALL be stored in a relational database (SQLite by default, PostgreSQL as optional upgrade). |

### 4.2 Query Pipeline

#### FR-6: Query Processing

| ID | Requirement |
|---|---|
| FR-6.1 | The system SHALL support multi-query expansion: given a user query, generate 2-3 alternative phrasings via LLM to improve recall. All phrasings are searched independently and results merged. |
| FR-6.2 | Multi-query expansion SHALL be configurable (enable/disable) to allow low-latency mode for simple queries. |

#### FR-7: Hybrid Retrieval

| ID | Requirement |
|---|---|
| FR-7.1 | The system SHALL perform hybrid search combining dense vector similarity and sparse BM25 keyword matching. |
| FR-7.2 | Results from dense and sparse retrieval SHALL be merged using Reciprocal Rank Fusion (RRF) with a configurable k parameter (default k=60). |
| FR-7.3 | The system SHALL retrieve a configurable number of initial candidates (default: 20) before reranking. |
| FR-7.4 | The system SHALL support filtering by collection, document, date range, and custom metadata tags during retrieval. |
| FR-7.5 | The system SHALL support searching across multiple collections in a single query. |

#### FR-8: Reranking

| ID | Requirement |
|---|---|
| FR-8.1 | The system SHALL rerank retrieved candidates using a dedicated reranking model, NOT a general-purpose LLM. |
| FR-8.2 | The default reranker SHALL be Cohere Rerank 3.5. |
| FR-8.3 | The system SHALL support the following reranker providers via a common interface: Cohere Rerank, cross-encoder models (local, via sentence-transformers), and BGE-reranker-v2-m3 (local). |
| FR-8.4 | The reranker SHALL reduce the candidate set to a configurable number of final chunks (default: 5) for context assembly. |
| FR-8.5 | Reranking scores SHALL be preserved in the response for transparency and debugging. |

#### FR-9: Corrective RAG

| ID | Requirement |
|---|---|
| FR-9.1 | After reranking, the system SHALL evaluate whether the top-ranked chunks are relevant to the query using an LLM relevance check. |
| FR-9.2 | If the relevance score falls below a configurable threshold, the system SHALL automatically reformulate the query and perform a second retrieval pass. |
| FR-9.3 | The system SHALL perform at most 2 retrieval attempts (initial + one retry) to bound latency. |
| FR-9.4 | If both attempts fail to find relevant context, the system SHALL inform the user that the available documents do not contain sufficient information to answer the query, rather than hallucinating an answer. |
| FR-9.5 | Corrective RAG SHALL be configurable (enable/disable) for latency-sensitive use cases. |

#### FR-10: Answer Generation

| ID | Requirement |
|---|---|
| FR-10.1 | The system SHALL generate answers using a configurable LLM provider. |
| FR-10.2 | The system SHALL support the following LLM providers via a common interface: Anthropic (Claude), OpenAI (GPT), Ollama (local models), and any OpenAI-compatible API endpoint. Provider routing SHALL be handled via LiteLLM. |
| FR-10.3 | The system SHALL stream responses to the frontend via WebSocket for real-time display. |
| FR-10.4 | The system SHALL include source citations in every answer: document name, page number(s), section header, and relevance score for each referenced chunk. |
| FR-10.5 | The system SHALL provide the retrieved chunks alongside the generated answer so the user can inspect the source material. |
| FR-10.6 | The system prompt SHALL instruct the LLM to answer only from provided context, acknowledge when context is insufficient, and never fabricate information. |
| FR-10.7 | The system SHALL support configurable system prompts for different use cases (e.g., summarization, Q&A, analysis). |

#### FR-11: Parent-Child Context Expansion

| ID | Requirement |
|---|---|
| FR-11.1 | When a small chunk is retrieved, the system SHALL have the option to expand context by retrieving its parent chunk (the enclosing section). |
| FR-11.2 | Context expansion SHALL be configurable: off (return matched chunk only), parent (return enclosing section), or siblings (return matched chunk plus adjacent chunks). |
| FR-11.3 | The total assembled context SHALL respect a configurable token budget (default: 8,000 tokens) to stay within LLM context limits. |

### 4.3 Frontend

#### FR-12: Document Management

| ID | Requirement |
|---|---|
| FR-12.1 | The frontend SHALL provide a document upload interface supporting drag-and-drop and file picker for PDF files. |
| FR-12.2 | The frontend SHALL display upload and processing progress per document (parsing, chunking, embedding, complete, failed). |
| FR-12.3 | The frontend SHALL display a document library showing all ingested documents with metadata (title, page count, chunk count, upload date, status). |
| FR-12.4 | The frontend SHALL support creating, renaming, and deleting collections, and assigning documents to collections. |
| FR-12.5 | The frontend SHALL support re-ingesting a document (e.g., with different parser or chunking settings). |
| FR-12.6 | The frontend SHALL support bulk upload of multiple PDFs. |

#### FR-13: Chat Interface

| ID | Requirement |
|---|---|
| FR-13.1 | The frontend SHALL provide a conversational chat interface for querying documents. |
| FR-13.2 | The chat interface SHALL display streaming LLM responses in real-time. |
| FR-13.3 | Each answer SHALL display inline source citations linked to the source chunks. |
| FR-13.4 | The user SHALL be able to click a source citation to view the full chunk text, document name, page number, and relevance score. |
| FR-13.5 | The frontend SHALL support multiple chat sessions (conversations) with independent history. |
| FR-13.6 | The user SHALL be able to select which collection(s) to search against for each conversation. |
| FR-13.7 | The chat interface SHALL support follow-up questions within the same conversation, with previous Q&A pairs available as context. |

#### FR-14: Settings & Configuration

| ID | Requirement |
|---|---|
| FR-14.1 | The frontend SHALL provide a settings page to configure LLM provider, embedding provider, and reranker provider with API keys and model selection. |
| FR-14.2 | The frontend SHALL provide controls for retrieval parameters: chunk count, reranking top-k, context expansion mode, multi-query expansion toggle, corrective RAG toggle. |
| FR-14.3 | The frontend SHALL provide controls for ingestion parameters: parser selection (Docling / PyMuPDF4LLM / vision), chunk size, chunk overlap, contextual enrichment toggle. |

### 4.4 System Administration

#### FR-15: Health & Observability

| ID | Requirement |
|---|---|
| FR-15.1 | The backend SHALL expose a `/health` endpoint reporting status of all dependencies (Qdrant, LLM provider, embedding provider). |
| FR-15.2 | The system SHALL log all queries, retrieval results, reranking scores, and generation calls for debugging and evaluation. |
| FR-15.3 | Logs SHALL be structured (JSON) and configurable in verbosity level. |

### 4.5 Experiment Harness

This section captures requirements added in Sprint 7 to support the
RAG vs LLM Wiki experiment: per-document metadata for corpus
labeling, telemetry needed to test the efficiency hypothesis,
extended-thinking configuration to match the Wiki side, and CLI
tooling to drive ingestion / question-running / judging at scale.

#### FR-16: Document Tags

| ID | Requirement |
|---|---|
| FR-16.1 | The system SHALL accept arbitrary key/value metadata per document via a `tags_json` multipart field on `POST /api/documents/upload`, validated as a JSON object. |
| FR-16.2 | Document tags SHALL be persisted in a JSON column on the `documents` table and returned via every document response. |
| FR-16.3 | Tag values SHALL be free-form (string, number, boolean) so callers can encode experiment-specific schemas (e.g. `{"domain": "ai-ethics-law", "role": "Anchor", "year": 2026, "authors": "Stober & Dornis"}`) without server-side schema changes. |

#### FR-17: Per-Document Ingestion Timing

| ID | Requirement |
|---|---|
| FR-17.1 | The system SHALL record `started_at` and `completed_at` timestamps per `IngestionJob` row, set by the pipeline at job start and at terminal status transition. |
| FR-17.2 | `GET /api/documents` and `GET /api/documents/{id}` SHALL surface the latest job's `ingestion_started_at`, `ingestion_completed_at`, and computed `ingestion_seconds` in their response payloads. |
| FR-17.3 | The aggregated per-document timings SHALL be exportable in a stable JSON shape suitable for direct comparison against external systems (see §4.5 FR-20). |

#### FR-18: Token-Usage Telemetry

| ID | Requirement |
|---|---|
| FR-18.1 | The system SHALL capture `prompt_tokens`, `completion_tokens`, and (for Anthropic extended-thinking models) `thinking_tokens` from every answer-generation call. |
| FR-18.2 | Token counts SHALL be returned in `QueryResponse.metadata` and emitted as a `{"type": "usage"}` event over the WebSocket streaming endpoint. |
| FR-18.3 | Token counts SHALL be persisted on the assistant `Message` row alongside `model_used` and `latency_ms` so conversations are usable as an experiment audit log. |
| FR-18.4 | For streaming generation, the system SHALL request `stream_options={"include_usage": true}` so the final stream chunk carries usage data. |

#### FR-19: Extended-Thinking Configuration (Adaptive Thinking)

Anthropic's manual extended-thinking mode (`thinking: {type: "enabled",
budget_tokens: N}`) is **rejected with HTTP 400 on Claude Opus 4.7**.
The supported configuration is adaptive thinking with a separate
effort tier passed via `output_config`.

| ID | Requirement |
|---|---|
| FR-19.1 | The system SHALL pass `thinking={"type": "adaptive", "display": "summarized"}` to the LLM call when thinking is enabled. The `display: "summarized"` setting is required because Opus 4.7 silently flipped the default to `"omitted"`; without it the response carries an empty `thinking` field, hiding reasoning traces from human reviewers. |
| FR-19.2 | The system SHALL pass `output_config={"effort": <tier>}` at the top level of the request alongside the adaptive `thinking` block, where `<tier> ∈ {low, medium, high, xhigh, max}`. Effort acts as soft guidance for how much thinking Claude allocates per request. |
| FR-19.3 | A `reasoning_effort` setting (`off` / `low` / `medium` / `high` / `xhigh` / `max`) SHALL be configurable via `REASONING_EFFORT` env var with per-request override in `QueryRequest.options.reasoning_effort`. The value `off` SHALL omit the `thinking` block entirely (Opus 4.7's default-off behavior). The value `xhigh` is Opus-4.7-specific; `max` is Anthropic's absolute ceiling. |
| FR-19.4 | Whenever thinking is enabled, the system SHALL force `temperature=1.0` (historical Anthropic constraint, harmless on adaptive thinking which would default to 1.0 anyway) and SHALL set `max_tokens` to a generous ceiling (default 16,000) — `max_tokens` is a hard cap on total output (thinking + answer) and at xhigh/max the model can exhaust a small cap before producing answer text. Otherwise the system SHALL use the configured `generation_temperature` (default 0.2). |
| FR-19.5 | The system SHALL NEVER emit `thinking={"type": "enabled", "budget_tokens": N}` on the answer-generation path. Regression tests (`test_thinking.py::test_no_budget_tokens_anywhere`, `test_generator.py::test_generate_never_emits_budget_tokens`) cover this. |
| FR-19.6 | The system SHALL support a separate model for ingestion-time contextual enrichment (`ENRICHMENT_LLM_MODEL`, default `claude-sonnet-4-5-20250929`) so per-chunk summarization can run on a cheaper model without affecting answer-generation quality. The enrichment path SHALL NOT enable thinking — Sonnet 4.5 still accepts manual `budget_tokens` (deprecated but functional), but our enrichment is summarization-shaped, not reasoning-heavy, so we run it without thinking. |

**Reference:** [Anthropic adaptive-thinking docs](https://platform.claude.com/docs/en/docs/build-with-claude/adaptive-thinking).

#### FR-20: Batch Ingestion CLI

| ID | Requirement |
|---|---|
| FR-20.1 | The system SHALL provide a `rag2compare-ingest` console entry point (and `python -m scripts.ingest_corpus` invocation) that drives `POST /api/collections` and `POST /api/documents/upload` from a YAML manifest. |
| FR-20.2 | The CLI SHALL sort each collection's documents by role using a configurable `ingest_order` (default `Anchor → Chrono → Bridge → Conflict`) and stamp the manifest's per-document tags onto each upload. |
| FR-20.3 | The CLI SHALL poll each document's status to a terminal state and write `experiments/results/ingest-<timestamp>.json` containing per-document timings, status, and chunk counts plus per-domain totals. |
| FR-20.4 | The CLI SHALL support `--dry-run` (print plan without uploading), `--only <substr>` (filter to specific files), `--skip-completed` (resume after interruption), and configurable `--poll-interval` / `--poll-timeout`. |

#### FR-21: Experiment Runner CLI

| ID | Requirement |
|---|---|
| FR-21.1 | The system SHALL provide a `rag2compare-run` console entry point that submits a YAML question set to `POST /api/query` and writes the answers, sources, and metadata to `experiments/results/run-<timestamp>.json`. |
| FR-21.2 | Each question SHALL be submitted in a fresh conversation (no carried context) by default, so cross-question memory contamination is avoided. |
| FR-21.3 | The CLI SHALL accept `--reasoning-effort` to override the server-side default per-run, and `--repeat N` to support consistency testing. |
| FR-21.4 | The CLI SHALL support `--only-tier`, `--only-id`, `--collections`, and `--dry-run` for selective and offline use. |

#### FR-22: Judge LLM CLI

| ID | Requirement |
|---|---|
| FR-22.1 | The system SHALL provide a `rag2compare-judge` console entry point that pairs a RAG `run-*.json` and a Wiki `run-*.json` by question id and scores both with a configurable Judge LLM. |
| FR-22.2 | The judge SHALL blind each question's answers as System A / System B with a seeded RNG; the assignment SHALL be recorded in the output for un-blinding during analysis. |
| FR-22.3 | The judge SHALL score both systems independently against a YAML-defined rubric (criterion id, label, description, anchored 1/5/10 definitions). |
| FR-22.4 | The default judge model SHALL be cross-family with respect to the answer-generation model (default `gpt-5` when answer model is Claude) to avoid documented same-family self-preference bias in LLM-as-a-judge scoring. |
| FR-22.5 | The judge SHALL emit `experiments/results/judged-<timestamp>.json` containing per-question scores, judge notes, raw response, blinding mapping, and aggregated means per system per criterion per tier. |
| FR-22.6 | The judge SHALL support `--secondary-judge MODEL --secondary-judge-questions <ids>` for inter-rater reliability spot-checks, with per-criterion max-delta agreement reported in the output. |
| FR-22.7 | The judge SHALL support `--resume <prior-judged-file>` to skip questions already scored by the same judge model. |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| ID | Requirement |
|---|---|
| NFR-1.1 | Query-to-first-token latency SHALL be < 3 seconds for standard queries (no multi-query expansion, no corrective RAG). |
| NFR-1.2 | End-to-end query latency (full answer) SHALL be < 10 seconds at p95 with all pipeline features enabled. |
| NFR-1.3 | Document ingestion throughput SHALL sustain >= 10 pages/second for text-heavy PDFs (Docling parser). |
| NFR-1.4 | The system SHALL support 20 concurrent query requests without degradation. |

### 5.2 Reliability

| ID | Requirement |
|---|---|
| NFR-2.1 | The system SHALL gracefully handle provider API failures with retry logic (3 attempts, exponential backoff). |
| NFR-2.2 | A failed document ingestion SHALL NOT corrupt existing data. Ingestion is atomic per document. |
| NFR-2.3 | The system SHALL persist all vector data and metadata to disk. No data loss on process restart. |

### 5.3 Security

| ID | Requirement |
|---|---|
| NFR-3.1 | API keys and secrets SHALL be stored in environment variables or a `.env` file, never in code or database. |
| NFR-3.2 | The backend SHALL validate and sanitize all file uploads (file type, file size limits, filename sanitization). |
| NFR-3.3 | Maximum upload file size SHALL be configurable (default: 100 MB per file). |
| NFR-3.4 | The system SHALL NOT expose uploaded documents or internal API keys through the frontend API without authentication. |

### 5.4 Extensibility

| ID | Requirement |
|---|---|
| NFR-4.1 | All provider integrations (LLM, embedding, reranker, parser) SHALL implement a common abstract interface, allowing new providers to be added without modifying existing code. |
| NFR-4.2 | The ingestion and query pipelines SHALL be composed of discrete, independently testable stages. |
| NFR-4.3 | The system SHALL support additional document types (DOCX, PPTX, HTML) in future without architectural changes (Docling already supports these). |

### 5.5 Testability

| ID | Requirement |
|---|---|
| NFR-5.1 | The system SHALL include unit tests for all pipeline stages with >= 80% code coverage. |
| NFR-5.2 | The system SHALL include integration tests for the full ingestion and query pipelines. |
| NFR-5.3 | The system SHALL include a RAG evaluation suite (see Section 9). |

---

## 6. Technology Selections

### 6.1 Backend Stack

| Component | Selection | Rationale |
|---|---|---|
| **Language** | Python 3.12 | Ecosystem compatibility, ML library support |
| **Web framework** | FastAPI | Async support, auto-generated OpenAPI docs, WebSocket support, high performance |
| **Task queue** | asyncio + background tasks (FastAPI) | Sufficient for medium scale; Celery as optional upgrade |
| **Metadata DB** | SQLite (default) / PostgreSQL (optional) | SQLite is zero-config for local deployment; SQLAlchemy ORM for portability |
| **ORM** | SQLAlchemy 2.0 | Provider-agnostic, async support, mature |

### 6.2 Frontend Stack

| Component | Selection | Rationale |
|---|---|---|
| **Framework** | Next.js 15 (App Router) | SSR/SSG flexibility, file-based routing, React Server Components |
| **UI library** | shadcn/ui + Tailwind CSS | Composable components, no runtime overhead, excellent DX |
| **State management** | Zustand | Lightweight, minimal boilerplate vs Redux |
| **Data fetching** | TanStack Query (React Query) | Caching, optimistic updates, background refetching |
| **Streaming** | Native WebSocket | Real-time LLM response streaming |

### 6.3 PDF Processing

| Component | Selection | Rationale |
|---|---|---|
| **Primary parser** | Docling (IBM) | AI-powered layout analysis, table extraction, Markdown output, OSS |
| **Fast fallback** | PyMuPDF4LLM | 50x faster than Docling, good for text-heavy bulk processing |
| **Vision parser** | Multimodal LLM (provider-agnostic) | For charts/diagrams; renders pages to images, sends to VLM |
| **OCR** | Docling integrated (Tesseract/EasyOCR) | Handles scanned pages automatically |

### 6.4 Chunking

| Component | Selection | Rationale |
|---|---|---|
| **Structural splitter** | `MarkdownHeaderTextSplitter` (LangChain) | Respects document hierarchy from Docling Markdown output |
| **Size splitter** | `RecursiveCharacterTextSplitter` (LangChain) | Secondary pass to enforce token limits on oversized structural chunks |
| **Token counter** | `tiktoken` | Accurate token counting for OpenAI-compatible models |

### 6.5 Embedding

| Component | Selection | Rationale |
|---|---|---|
| **Default provider** | OpenAI `text-embedding-3-large` (1024d) | Strong MTEB scores, Matryoshka support, reliable API |
| **Premium option** | Cohere `embed-v4` (1024d) | 128K context, multimodal, best-in-class for RAG |
| **Local option** | Sentence-Transformers / Ollama | Offline capability, no API cost |
| **Sparse vectors** | BM25 via `rank_bm25` or Qdrant built-in sparse encoding | Keyword matching for hybrid search |

### 6.6 Vector Store

| Component | Selection | Rationale |
|---|---|---|
| **Vector database** | Qdrant (Docker, self-hosted) | Native hybrid search (dense + sparse), Rust performance, named vectors, advanced filtering, production-grade at medium scale |
| **Client** | `qdrant-client` (Python) | Official client with async support |

### 6.7 Reranking

| Component | Selection | Rationale |
|---|---|---|
| **Default provider** | Cohere Rerank 3.5 | SOTA on BEIR, 100+ languages, fast, cost-effective |
| **Local option** | `BAAI/bge-reranker-v2-m3` (cross-encoder) | Best open-source multilingual reranker, self-hostable |

### 6.8 LLM

| Component | Selection | Rationale |
|---|---|---|
| **Router** | LiteLLM | Unified interface for 100+ LLM providers, drop-in OpenAI-compatible proxy |
| **Default answer-generation model** | Anthropic Claude Opus 4.7 with `xhigh` extended thinking (32K thinking budget) | Strong reasoning for synthesis-heavy queries; matches the LLM Wiki experiment counterpart for fair comparison |
| **Default enrichment model** | Anthropic Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) | Per-chunk contextual summarization is summarization-shaped, not reasoning-heavy — running Opus on ~1000 enrichment calls would inflate ingestion cost ~10× without quality benefit |
| **Default judge model** (experiment harness) | OpenAI GPT-5 with `medium` reasoning effort | Cross-family choice — avoids documented self-preference bias when scoring Claude outputs |
| **Alternatives** | OpenAI GPT-4.1 / GPT-5, Ollama (local), any LiteLLM-supported model | Provider-agnostic; per-call model override supported via `create_llm_provider(settings, model_override=...)` |

### 6.9 Evaluation

| Component | Selection | Rationale |
|---|---|---|
| **RAG evaluation** | RAGAS | Industry standard, reference-free, comprehensive metrics |
| **CI/CD testing** | DeepEval | pytest-compatible, threshold-based quality gates |
| **Observability** | Arize Phoenix (optional) | Open-source tracing and evaluation dashboard |

### 6.10 Infrastructure

| Component | Selection | Rationale |
|---|---|---|
| **Containerization** | Docker + Docker Compose | Local deployment, reproducible environments |
| **Python packaging** | uv + pyproject.toml | Fast dependency resolution, modern Python packaging |
| **Node packaging** | pnpm | Fast, disk-efficient, strict dependency resolution |
| **Testing (backend)** | pytest + pytest-asyncio | Standard Python testing, async support |
| **Testing (frontend)** | Vitest + React Testing Library | Fast, Vite-native, good DX |
| **Linting (backend)** | Ruff | Fast, replaces flake8 + isort + pyupgrade |
| **Linting (frontend)** | ESLint + Prettier | Standard JS/TS tooling |

---

## 7. Data Model

### 7.1 Relational Schema (SQLite/PostgreSQL)

```
┌─────────────────────────┐       ┌─────────────────────────────┐
│       collections       │       │          documents           │
├─────────────────────────┤       ├─────────────────────────────┤
│ id           UUID (PK)  │◄──┐   │ id              UUID (PK)   │
│ name         TEXT        │   │   │ collection_id   UUID (FK)   │──┐
│ description  TEXT        │   │   │ filename        TEXT         │  │
│ created_at   TIMESTAMP   │   │   │ title           TEXT         │  │
│ updated_at   TIMESTAMP   │   │   │ author          TEXT         │  │
└─────────────────────────┘   │   │ page_count      INTEGER      │  │
                              │   │ file_size_bytes INTEGER      │  │
                              │   │ file_hash       TEXT (SHA256)│  │
                              │   │ language        TEXT          │  │
                              │   │ status          ENUM         │  │
                              │   │ parser_used     TEXT          │  │
                              │   │ chunk_count     INTEGER      │  │
                              │   │ embedding_model TEXT          │  │
                              │   │ created_at      TIMESTAMP    │  │
                              │   │ updated_at      TIMESTAMP    │  │
                              │   └─────────────────────────────┘  │
                              │                                    │
                              │   ┌─────────────────────────────┐  │
                              │   │       conversations          │  │
                              │   ├─────────────────────────────┤  │
                              │   │ id              UUID (PK)   │  │
                              └───│ collection_id   UUID (FK)   │  │
                                  │ title           TEXT         │  │
                                  │ created_at      TIMESTAMP   │  │
                                  │ updated_at      TIMESTAMP   │  │
                                  └──────────┬──────────────────┘  │
                                             │                     │
                                  ┌──────────▼──────────────────┐  │
                                  │        messages              │  │
                                  ├─────────────────────────────┤  │
                                  │ id              UUID (PK)   │  │
                                  │ conversation_id UUID (FK)   │  │
                                  │ role            ENUM        │  │
                                  │ content         TEXT         │  │
                                  │ sources         JSON        │  │
                                  │ created_at      TIMESTAMP   │  │
                                  └─────────────────────────────┘  │
                                                                   │
                              ┌────────────────────────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │      ingestion_jobs              │
              ├─────────────────────────────────┤
              │ id              UUID (PK)        │
              │ document_id     UUID (FK)        │
              │ status          ENUM             │
              │ parser          TEXT              │
              │ chunk_size      INTEGER           │
              │ chunk_overlap   INTEGER           │
              │ contextual_enrichment BOOLEAN     │
              │ error_message   TEXT              │
              │ started_at      TIMESTAMP         │
              │ completed_at    TIMESTAMP         │
              └─────────────────────────────────┘
```

**Enums:**
- `document.status`: `pending`, `parsing`, `chunking`, `enriching`, `embedding`, `complete`, `failed`
- `message.role`: `user`, `assistant`
- `ingestion_jobs.status`: `queued`, `running`, `complete`, `failed`

**Sprint 7 column additions** (per FR-16, FR-18):

| Table | Column | Type | Purpose |
|---|---|---|---|
| `documents` | `tags` | JSON, nullable | Free-form per-document metadata (FR-16) |
| `messages` | `model_used` | VARCHAR(100), nullable | Which LLM produced the assistant message |
| `messages` | `latency_ms` | INTEGER, nullable | End-to-end query latency |
| `messages` | `prompt_tokens` | INTEGER, nullable | Tokens sent to the model |
| `messages` | `completion_tokens` | INTEGER, nullable | Non-thinking tokens generated |
| `messages` | `thinking_tokens` | INTEGER, nullable | Anthropic extended-thinking budget consumed |

The system has no Alembic at this time; new nullable columns are
applied via idempotent `ALTER TABLE ADD COLUMN` statements in
`init_db()` after `Base.metadata.create_all`. Non-trivial future
migrations should adopt Alembic.

### 7.2 Qdrant Vector Schema

Each collection in Qdrant stores points with:

```json
{
  "id": "uuid",
  "vector": {
    "dense": [0.012, -0.034, ...],   // 1024-dim float32
    "sparse": {                       // BM25 sparse vector
      "indices": [102, 5043, 9821],
      "values": [0.8, 1.2, 0.6]
    }
  },
  "payload": {
    "document_id": "uuid",
    "filename": "report.pdf",
    "page_numbers": [12, 13],
    "header_chain": ["Chapter 3", "Section 3.2", "Revenue Analysis"],
    "chunk_index": 42,
    "chunk_token_count": 487,
    "chunk_text": "The full text of the chunk...",
    "contextual_summary": "This chunk is from Section 3.2 of the Q4 Report...",
    "parent_chunk_id": "uuid-of-parent",
    "embedding_model": "text-embedding-3-large"
  }
}
```

---

## 8. API Specification

### 8.1 REST Endpoints

#### Documents

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/documents/upload` | Upload one or more PDF files to a collection |
| `GET` | `/api/documents` | List all documents (filterable by collection, status) |
| `GET` | `/api/documents/{id}` | Get document details and metadata |
| `DELETE` | `/api/documents/{id}` | Delete document and its chunks from vector store |
| `POST` | `/api/documents/{id}/reingest` | Re-process document with new settings |

#### Collections

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/collections` | Create a new collection |
| `GET` | `/api/collections` | List all collections with document counts |
| `GET` | `/api/collections/{id}` | Get collection details |
| `PUT` | `/api/collections/{id}` | Update collection name/description |
| `DELETE` | `/api/collections/{id}` | Delete collection and all its documents |

#### Query

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/query` | Submit a query; returns answer + sources (non-streaming) |
| `WS` | `/ws/query` | Submit a query; streams answer tokens via WebSocket |

#### Conversations

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/conversations` | Create a new conversation |
| `GET` | `/api/conversations` | List conversations |
| `GET` | `/api/conversations/{id}` | Get conversation with message history |
| `DELETE` | `/api/conversations/{id}` | Delete a conversation |

#### Settings & Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/settings` | Get current provider configuration |
| `PUT` | `/api/settings` | Update provider configuration |
| `GET` | `/api/health` | Health check for all dependencies |

### 8.2 Query Request/Response

**Request (`POST /api/query`):**
```json
{
  "query": "What was Q4 revenue?",
  "collection_ids": ["uuid-1", "uuid-2"],
  "conversation_id": "uuid (optional)",
  "options": {
    "top_k_retrieval": 20,
    "top_k_rerank": 5,
    "multi_query": true,
    "corrective_rag": true,
    "context_expansion": "parent",
    "max_context_tokens": 8000,
    "reasoning_effort": "xhigh"
  }
}
```

`options.reasoning_effort` (added in v1.1, FR-19) overrides the
server-side default. Accepted values: `off | low | medium | high | xhigh`.

**Response:**
```json
{
  "answer": "Q4 revenue was $2.3 billion, representing a 15% increase...",
  "sources": [
    {
      "document_id": "uuid",
      "filename": "Q4_Report.pdf",
      "page_numbers": [12],
      "header_chain": ["Financial Results", "Revenue"],
      "chunk_text": "Q4 2024 revenue reached $2.3 billion...",
      "relevance_score": 0.94
    }
  ],
  "metadata": {
    "retrieval_count": 20,
    "reranked_count": 5,
    "corrective_rag_triggered": false,
    "query_variations": ["What was the revenue in Q4?", "Q4 quarterly revenue figures"],
    "latency_ms": 2340,
    "model_used": "claude-opus-4-7",
    "reasoning_effort": "xhigh",
    "prompt_tokens": 4031,
    "completion_tokens": 612,
    "thinking_tokens": 18044
  }
}
```

The `reasoning_effort` and `*_tokens` fields were added in v1.1 (FR-18,
FR-19). They are nullable: a non-thinking model run will report
`reasoning_effort: "off"` and null `thinking_tokens`.

**Document upload** accepts an optional `tags_json` multipart form
field carrying a JSON object that gets stamped onto every uploaded
document (FR-16). Example:

```bash
curl -F files=@paper.pdf \
     -F 'tags_json={"domain":"ai-ethics-law","role":"Anchor","year":2026}' \
     "http://localhost:8000/api/documents/upload?collection_id=<uuid>"
```

`DocumentResponse` includes `tags`, `ingestion_started_at`,
`ingestion_completed_at`, and `ingestion_seconds` (FR-17).

---

## 9. Evaluation & Quality Assurance

### 9.1 RAG Evaluation Framework

The system SHALL include an evaluation suite that measures retrieval and generation quality.

#### Metrics

| Metric | Tool | Target | Description |
|---|---|---|---|
| **Faithfulness** | RAGAS | >= 0.85 | Does the answer only contain information from the provided context? |
| **Answer Relevancy** | RAGAS | >= 0.80 | Does the answer actually address the user's question? |
| **Context Precision** | RAGAS | >= 0.75 | Are the retrieved chunks relevant to the query? |
| **Context Recall** | RAGAS | >= 0.70 | Did retrieval find all the relevant information? |
| **Latency (p95)** | Custom | < 5s (standard), < 10s (full pipeline) | End-to-end response time |
| **Cost per query** | Custom | Tracked | Total API cost (embedding + reranking + LLM) |

#### Evaluation Dataset

- A curated test set of >= 50 question-answer pairs across multiple documents
- Covers factual recall, table lookups, multi-document synthesis, and unanswerable questions
- Ground-truth answers provided for context recall measurement
- Maintained in `tests/eval/dataset.json`

#### CI/CD Integration

- DeepEval tests run on every PR as quality gates
- Faithfulness and Answer Relevancy thresholds enforced (fail PR if below threshold)
- Evaluation results logged and tracked over time

### 9.2 Testing Strategy

| Level | Scope | Tools |
|---|---|---|
| **Unit tests** | Individual pipeline stages (parser, chunker, embedder, retriever, reranker, generator) | pytest |
| **Integration tests** | Full ingestion pipeline, full query pipeline | pytest + test fixtures |
| **API tests** | All REST endpoints, WebSocket streaming | pytest + httpx |
| **Frontend tests** | Component rendering, user interactions | Vitest + React Testing Library |
| **E2E tests** | Upload → ingest → query → verify answer | Playwright |
| **RAG evaluation** | Retrieval and generation quality | RAGAS + DeepEval |

### 9.3 Experiment Evaluation: RAG vs LLM Wiki

The Sprint 7 experiment harness implements a controlled comparison
against an external LLM Wiki system over a shared 24-paper corpus.
The experimental construct, hypotheses, and execution procedure are
documented in [`docs/RUNBOOK.md`](./RUNBOOK.md). This section captures
the SRS-level requirements that the harness satisfies.

#### Experimental Construct

| Component | Specification |
|---|---|
| **Independent variable** | Knowledge architecture (Vector RAG vs LLM Wiki) |
| **Dependent variables** | Groundedness, Structural Integrity, Conflict Awareness, Inter-Paper Mapping (rubric-scored 1–10); per-document ingestion-time, per-query token cost (FR-17, FR-18) |
| **Corpus** | 24 papers across 3 domains (8 each: AI Ethics & Law, Climate Science, Precision Medicine), tagged Anchor / Chrono / Bridge / Conflict (FR-16) |
| **Question set** | 13 questions across 5 tiers (chronological, conflict, multi-hop, emergence, policy) plus 3 RAG-favoring point-source bias-checks |
| **Answer model (both systems)** | Claude Opus 4.7 with `xhigh` extended thinking (FR-19) |
| **Judge model** | GPT-5 with `medium` reasoning, with optional second-judge spot-check (FR-22) |

#### Hypotheses

- **H1 (Synthesis advantage):** LLM Wiki ≥ RAG + 2.0 mean on `inter_paper_mapping` and `structural_integrity` for `multi-hop` and `emergence` tiers.
- **H2 (Fact-retrieval baseline):** Vector RAG ≥ LLM Wiki on `groundedness` for the `bias-check` tier.
- **H3 (Efficiency tradeoff):** LLM Wiki ingestion-time and ingestion-tokens substantially exceed RAG's; RAG per-query token cost (especially `thinking_tokens` at `xhigh`) substantially exceeds the LLM Wiki's.

#### Required Artifacts

| Artifact | Producer | Tested by FR-* |
|---|---|---|
| `experiments/corpus.yaml` | Hand-authored, ingest CLI consumes | FR-20 |
| `experiments/questions.yaml` | Hand-authored, runner CLI consumes | FR-21 |
| `experiments/rubric.yaml` | Hand-authored, judge CLI consumes | FR-22 |
| `experiments/results/ingest-<ts>.json` | `rag2compare-ingest` | FR-17, FR-20 |
| `experiments/results/run-<ts>.json` | `rag2compare-run` | FR-18, FR-21 |
| `experiments/results/judged-<ts>.json` | `rag2compare-judge` | FR-22 |

#### Bias Controls

| Control | Mechanism |
|---|---|
| Same answer model both sides | Both systems use Claude Opus 4.7 + xhigh; isolates architecture as the IV |
| Memory contamination | Runner submits each question in a fresh conversation by default (FR-21.2) |
| Position / ordering bias | Judge blinds A/B per question with a seeded RNG (FR-22.2) |
| Same-family judge bias | Default judge is cross-family (`gpt-5`) when answer model is Claude (FR-22.4) |
| Judge calibration drift | Inter-rater reliability spot-check via `--secondary-judge` flag (FR-22.6) |
| Strict context limits | `max_context_tokens` is a hard ceiling — system cannot silently expand into long-context "stuffing" mode (FR-11.3) |

---

## 10. Migration Strategy

### 10.1 Phased Approach

The migration from v1.0 to v2.0 is structured in phases, each delivering independent value:

#### Phase 1: Foundation
- Set up project structure (monorepo with `backend/` and `frontend/`)
- FastAPI backend with provider abstraction layer
- Qdrant integration with hybrid search (dense + sparse)
- Migrate existing ChromaDB data to Qdrant
- Basic REST API for document upload and query
- Unit and integration test foundation

#### Phase 2: Ingestion Pipeline
- Docling PDF parser integration (with PyMuPDF4LLM fallback)
- Document-aware chunking (Markdown splitter + recursive secondary pass)
- Contextual enrichment (LLM-generated chunk summaries)
- Parent-child chunk relationships
- Background ingestion with status tracking

#### Phase 3: Query Pipeline
- Multi-query expansion
- Cohere Rerank integration (with local cross-encoder fallback)
- Corrective RAG loop
- Parent-child context expansion
- Streaming answer generation via WebSocket

#### Phase 4: Frontend
- Next.js application with shadcn/ui
- Document upload and management UI
- Chat interface with streaming and source citations
- Collection management
- Settings and provider configuration

#### Phase 5: Evaluation & Polish
- RAGAS evaluation suite with curated test dataset
- DeepEval CI/CD quality gates
- Structured logging and observability
- Vision-based PDF parsing (optional parser mode)
- Docker Compose deployment configuration
- Documentation

### 10.2 Data Migration

- Existing ChromaDB data can be exported and re-ingested through the new pipeline
- Re-ingestion is recommended (rather than vector migration) since the new pipeline produces higher-quality chunks and embeddings
- The old Streamlit app remains functional during migration

---

## 11. Appendices

### Appendix A: Provider Interface Contracts

```python
# Embedding Provider Interface
class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    async def embed_query(self, query: str) -> list[float]: ...
    @property
    @abstractmethod
    def dimensions(self) -> int: ...
    @property
    @abstractmethod
    def model_name(self) -> str: ...

# LLM Provider Interface
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict], **kwargs) -> str: ...
    @abstractmethod
    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...

# Reranker Provider Interface
class RerankerProvider(ABC):
    @abstractmethod
    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]: ...
```

### Appendix B: Configuration Schema

```yaml
# config.yaml (example)
providers:
  embedding:
    provider: "openai"                    # openai | cohere | jina | sentence-transformers | ollama
    model: "text-embedding-3-large"
    dimensions: 1024
    api_key: "${OPENAI_API_KEY}"

  llm:
    provider: "anthropic"                 # anthropic | openai | ollama | litellm
    model: "claude-sonnet-4-5-20250929"
    api_key: "${ANTHROPIC_API_KEY}"

  reranker:
    provider: "cohere"                    # cohere | cross-encoder | bge-reranker
    model: "rerank-v3.5"
    api_key: "${COHERE_API_KEY}"

ingestion:
  parser: "docling"                       # docling | pymupdf4llm | vision
  chunk_size_tokens: 512
  chunk_overlap_tokens: 50
  contextual_enrichment: true

retrieval:
  top_k_retrieval: 20
  top_k_rerank: 5
  hybrid_search: true
  rrf_k: 60
  multi_query: true
  corrective_rag: true
  context_expansion: "parent"             # off | parent | siblings
  max_context_tokens: 8000

storage:
  qdrant_url: "http://localhost:6333"
  metadata_db: "sqlite:///data/metadata.db"
```

### Appendix C: Directory Structure (Target)

```
rag2compare/
├── docker-compose.yml
├── docs/
│   ├── SRS.md                            # This document
│   └── ...                               # Subsequent planning docs
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   ├── main.py                       # FastAPI app entry point
│   │   ├── config.py                     # Settings and configuration
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── documents.py
│   │   │   │   ├── collections.py
│   │   │   │   ├── query.py
│   │   │   │   ├── conversations.py
│   │   │   │   └── settings.py
│   │   │   └── websocket.py
│   │   ├── models/                       # SQLAlchemy models
│   │   │   ├── document.py
│   │   │   ├── collection.py
│   │   │   ├── conversation.py
│   │   │   └── message.py
│   │   ├── schemas/                      # Pydantic schemas
│   │   ├── providers/
│   │   │   ├── base.py                   # Abstract interfaces
│   │   │   ├── embedding/
│   │   │   │   ├── openai.py
│   │   │   │   ├── cohere.py
│   │   │   │   ├── jina.py
│   │   │   │   ├── sentence_transformers.py
│   │   │   │   └── ollama.py
│   │   │   ├── llm/
│   │   │   │   ├── anthropic.py
│   │   │   │   ├── openai.py
│   │   │   │   ├── ollama.py
│   │   │   │   └── litellm.py
│   │   │   └── reranker/
│   │   │       ├── cohere.py
│   │   │       └── cross_encoder.py
│   │   ├── pipelines/
│   │   │   ├── ingestion/
│   │   │   │   ├── parser.py             # PDF parsing (Docling, PyMuPDF4LLM, vision)
│   │   │   │   ├── chunker.py            # Document-aware chunking
│   │   │   │   ├── enricher.py           # Contextual enrichment
│   │   │   │   └── embedder.py           # Batch embedding
│   │   │   └── query/
│   │   │       ├── expander.py           # Multi-query expansion
│   │   │       ├── retriever.py          # Hybrid search (dense + sparse)
│   │   │       ├── reranker.py           # Reranking orchestration
│   │   │       ├── validator.py          # Corrective RAG
│   │   │       └── generator.py          # Answer generation
│   │   └── storage/
│   │       ├── qdrant.py                 # Qdrant client wrapper
│   │       └── database.py              # SQLAlchemy session management
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── eval/
│           ├── dataset.json              # Curated Q&A test set
│           └── test_rag_quality.py        # RAGAS + DeepEval tests
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── src/
│   │   ├── app/                          # Next.js App Router
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx                  # Chat interface (default)
│   │   │   ├── documents/
│   │   │   │   └── page.tsx              # Document management
│   │   │   ├── collections/
│   │   │   │   └── page.tsx              # Collection management
│   │   │   └── settings/
│   │   │       └── page.tsx              # Provider configuration
│   │   ├── components/
│   │   │   ├── ui/                       # shadcn/ui components
│   │   │   ├── chat/
│   │   │   ├── documents/
│   │   │   └── layout/
│   │   ├── lib/
│   │   │   ├── api.ts                    # API client
│   │   │   └── websocket.ts              # WebSocket client
│   │   └── stores/                       # Zustand stores
│   └── tests/
└── data/                                 # Gitignored — runtime data
    ├── uploads/
    └── metadata.db
```

---

*End of SRS document.*
