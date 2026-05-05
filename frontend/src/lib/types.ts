/**
 * TypeScript types mirroring backend Pydantic schemas.
 * Keep in sync with backend/src/schemas/__init__.py.
 */

// --- Collections ---
export interface CollectionCreate {
  name: string;
  description?: string | null;
}

export interface CollectionUpdate {
  name?: string | null;
  description?: string | null;
}

export interface CollectionResponse {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

// --- Documents ---
export type DocumentStatus =
  | "pending"
  | "parsing"
  | "chunking"
  | "enriching"
  | "embedding"
  | "storing"
  | "completed"
  | "error"
  | "failed"
  | "processing";

export interface DocumentTags {
  domain?: string;
  role?: string;
  year?: number | string;
  authors?: string;
  title?: string;
  [key: string]: string | number | boolean | null | undefined;
}

export interface DocumentResponse {
  id: string;
  collection_id: string;
  filename: string;
  title: string | null;
  author: string | null;
  page_count: number | null;
  file_size_bytes: number | null;
  status: DocumentStatus | string;
  parser_used: string | null;
  chunk_count: number | null;
  embedding_model: string | null;
  error_message: string | null;
  tags: DocumentTags | null;
  ingestion_started_at: string | null;
  ingestion_completed_at: string | null;
  ingestion_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface ReingestRequest {
  parser?: string | null;
  chunk_size_tokens?: number | null;
  chunk_overlap_tokens?: number | null;
  contextual_enrichment?: boolean | null;
}

// --- Query ---
export type ReasoningEffort = "off" | "low" | "medium" | "high" | "xhigh";

export interface QueryOptions {
  top_k_retrieval?: number;
  top_k_rerank?: number;
  multi_query?: boolean;
  corrective_rag?: boolean;
  context_expansion?: "off" | "parent" | "siblings";
  max_context_tokens?: number;
  reasoning_effort?: ReasoningEffort | null;
}

export interface QueryRequest {
  query: string;
  collection_ids: string[];
  conversation_id?: string | null;
  options?: QueryOptions;
}

export interface SourceResponse {
  document_id: string;
  filename: string;
  page_numbers: number[];
  header_chain: string[];
  chunk_text: string;
  relevance_score: number;
}

export interface QueryUsage {
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  thinking_tokens?: number | null;
  total_tokens?: number | null;
}

export interface QueryMetadata {
  retrieval_count: number;
  reranked_count: number;
  corrective_rag_triggered: boolean;
  query_variations: string[];
  latency_ms: number;
  model_used: string;
  reasoning_effort?: ReasoningEffort | string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  thinking_tokens?: number | null;
}

export interface QueryResponse {
  answer: string;
  sources: SourceResponse[];
  metadata: QueryMetadata;
}

// --- Conversations ---
export interface ConversationCreate {
  collection_id: string;
  title?: string;
}

export interface MessageResponse {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: string | null;
  created_at: string;
}

export interface ConversationResponse {
  id: string;
  collection_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: MessageResponse[];
}

// --- Settings ---
export interface SettingsResponse {
  embedding_provider: string;
  embedding_model: string;
  embedding_dimensions: number;
  llm_provider: string;
  llm_model: string;
  enrichment_llm_model: string | null;
  reasoning_effort: string;
  reranker_provider: string;
  reranker_model: string;
  parser: string;
  chunk_size_tokens: number;
  chunk_overlap_tokens: number;
  contextual_enrichment: boolean;
  top_k_retrieval: number;
  top_k_rerank: number;
  hybrid_search: boolean;
  multi_query: boolean;
  corrective_rag: boolean;
  context_expansion: string;
  max_context_tokens: number;
}

// --- Health ---
export interface DependencyStatus {
  status: "ok" | "error";
  message: string | null;
}

export interface HealthResponse {
  status: string;
  qdrant: DependencyStatus;
  embedding_provider: DependencyStatus;
  llm_provider: DependencyStatus;
}

// --- WebSocket ---
export type WSMessageType = "token" | "sources" | "usage" | "metadata" | "done" | "error";

export interface WSMessage {
  type: WSMessageType;
  content?: string | SourceResponse[] | QueryMetadata | QueryUsage;
}
