"use client";

import { useQuery } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type { HealthResponse, SettingsResponse } from "@/lib/types";

export function useServerSettings() {
  return useQuery<SettingsResponse>({
    queryKey: ["server-settings"],
    queryFn: () => api.getSettings(),
  });
}

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    refetchInterval: 15_000,
  });
}
