/**
 * Typed API client for the Rag2Compare backend.
 *
 * All endpoints are prefixed with /api — the Next.js dev server proxies
 * these to the FastAPI backend via next.config.ts rewrites.
 */

import type {
  CollectionCreate,
  CollectionResponse,
  CollectionUpdate,
  ConversationCreate,
  ConversationResponse,
  DocumentResponse,
  HealthResponse,
  QueryRequest,
  QueryResponse,
  ReingestRequest,
  SettingsResponse,
} from "./types";

const BASE_URL = "/api";

class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown,
  ) {
    super(`API Error ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, res.statusText, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Health ---
export function getHealth(): Promise<HealthResponse> {
  return request("/health");
}

// --- Collections ---
export function listCollections(): Promise<CollectionResponse[]> {
  return request("/collections");
}

export function getCollection(id: string): Promise<CollectionResponse> {
  return request(`/collections/${id}`);
}

export function createCollection(data: CollectionCreate): Promise<CollectionResponse> {
  return request("/collections", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateCollection(
  id: string,
  data: CollectionUpdate,
): Promise<CollectionResponse> {
  return request(`/collections/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteCollection(id: string): Promise<void> {
  return request(`/collections/${id}`, { method: "DELETE" });
}

// --- Documents ---
export function listDocuments(collectionId?: string): Promise<DocumentResponse[]> {
  const query = collectionId ? `?collection_id=${collectionId}` : "";
  return request(`/documents${query}`);
}

export function getDocument(id: string): Promise<DocumentResponse> {
  return request(`/documents/${id}`);
}

/**
 * Upload one or more PDFs to a collection.
 *
 * Optional `tags` are JSON-encoded into the `tags_json` form field and stamped
 * on every uploaded document in the batch — the experiment uses this to label
 * each paper with domain/role/year/authors. Passing `tags: null` on a single
 * file behaves the same as omitting it.
 *
 * Returns one DocumentResponse per uploaded file (the API returns a list).
 */
export async function uploadDocuments(
  collectionId: string,
  files: File[],
  tags?: Record<string, unknown> | null,
): Promise<DocumentResponse[]> {
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }
  if (tags && Object.keys(tags).length > 0) {
    formData.append("tags_json", JSON.stringify(tags));
  }

  // The backend reads collection_id as a query parameter (string) and the
  // file list + tags_json as multipart fields.
  const url = `${BASE_URL}/documents/upload?collection_id=${encodeURIComponent(collectionId)}`;
  const res = await fetch(url, {
    method: "POST",
    body: formData,
    // Don't set Content-Type — browser sets it with boundary
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, res.statusText, body);
  }
  return res.json();
}

/** Single-file convenience wrapper around uploadDocuments. */
export async function uploadDocument(
  collectionId: string,
  file: File,
  tags?: Record<string, unknown> | null,
): Promise<DocumentResponse> {
  const [doc] = await uploadDocuments(collectionId, [file], tags);
  return doc;
}

export function reingestDocument(
  id: string,
  data?: ReingestRequest,
): Promise<DocumentResponse> {
  return request(`/documents/${id}/reingest`, {
    method: "POST",
    body: JSON.stringify(data ?? {}),
  });
}

export function deleteDocument(id: string): Promise<void> {
  return request(`/documents/${id}`, { method: "DELETE" });
}

// --- Query ---
export function submitQuery(data: QueryRequest): Promise<QueryResponse> {
  return request("/query", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// --- Conversations ---
export function listConversations(): Promise<ConversationResponse[]> {
  return request("/conversations");
}

export function getConversation(id: string): Promise<ConversationResponse> {
  return request(`/conversations/${id}`);
}

export function createConversation(
  data: ConversationCreate,
): Promise<ConversationResponse> {
  return request("/conversations", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function deleteConversation(id: string): Promise<void> {
  return request(`/conversations/${id}`, { method: "DELETE" });
}

// --- Settings ---
export function getSettings(): Promise<SettingsResponse> {
  return request("/settings");
}

export { ApiError };
