"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type {
  DocumentResponse,
  ReingestRequest,
} from "@/lib/types";

const DOCUMENTS_KEY = "documents";

const NON_TERMINAL_STATUSES = new Set([
  "pending",
  "parsing",
  "chunking",
  "enriching",
  "embedding",
  "storing",
  "processing",
]);

export function useDocuments(collectionId: string | null) {
  return useQuery<DocumentResponse[]>({
    queryKey: [DOCUMENTS_KEY, collectionId],
    queryFn: () => api.listDocuments(collectionId ?? undefined),
    enabled: collectionId !== null,
    // Auto-poll while any document is mid-pipeline so the UI ticks status
    // updates without a manual refresh.
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (!docs) return false;
      const hasInflight = docs.some((d) => NON_TERMINAL_STATUSES.has(d.status));
      return hasInflight ? 2000 : false;
    },
  });
}

export function useUploadDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      collectionId,
      files,
      tags,
    }: {
      collectionId: string;
      files: File[];
      tags?: Record<string, unknown> | null;
    }) => api.uploadDocuments(collectionId, files, tags),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: [DOCUMENTS_KEY, vars.collectionId] });
      qc.invalidateQueries({ queryKey: ["collections"] });
    },
  });
}

export function useReingestDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data?: ReingestRequest;
    }) => api.reingestDocument(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [DOCUMENTS_KEY] }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteDocument(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [DOCUMENTS_KEY] });
      qc.invalidateQueries({ queryKey: ["collections"] });
    },
  });
}
