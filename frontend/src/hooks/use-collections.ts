"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type {
  CollectionCreate,
  CollectionResponse,
  CollectionUpdate,
} from "@/lib/types";

const COLLECTIONS_KEY = ["collections"] as const;

export function useCollections() {
  return useQuery<CollectionResponse[]>({
    queryKey: COLLECTIONS_KEY,
    queryFn: () => api.listCollections(),
  });
}

export function useCollection(id: string | null) {
  return useQuery<CollectionResponse>({
    queryKey: ["collection", id],
    queryFn: () => api.getCollection(id as string),
    enabled: !!id,
  });
}

export function useCreateCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CollectionCreate) => api.createCollection(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  });
}

export function useUpdateCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CollectionUpdate }) =>
      api.updateCollection(id, data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: COLLECTIONS_KEY });
      qc.invalidateQueries({ queryKey: ["collection", vars.id] });
    },
  });
}

export function useDeleteCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  });
}
