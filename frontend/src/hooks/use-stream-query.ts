"use client";

import * as React from "react";
import { QueryWebSocket } from "@/lib/websocket";
import type {
  QueryMetadata,
  QueryOptions,
  QueryUsage,
  ReasoningEffort,
  SourceResponse,
} from "@/lib/types";

export interface StreamingTurn {
  id: string;
  question: string;
  answer: string;
  sources: SourceResponse[];
  usage: QueryUsage | null;
  metadata: QueryMetadata | null;
  status: "streaming" | "done" | "error";
  error?: string | null;
}

interface SubmitArgs {
  question: string;
  collectionIds: string[];
  reasoningEffort: ReasoningEffort;
}

/**
 * Drives a single QueryWebSocket connection across the chat session and
 * exposes a friendly turn-based view for the UI.
 *
 * The WebSocket URL falls back to the same host as the page on port 8000
 * for browser-served deployments. In local dev the default works because
 * Next.js's dev server (3000) and the FastAPI backend (8000) live side
 * by side on the user's machine.
 */
export function useStreamQuery(wsUrl?: string) {
  const [turns, setTurns] = React.useState<StreamingTurn[]>([]);
  const [isStreaming, setIsStreaming] = React.useState(false);
  const wsRef = React.useRef<QueryWebSocket | null>(null);
  const activeIdRef = React.useRef<string | null>(null);

  const updateActive = React.useCallback(
    (mut: (turn: StreamingTurn) => StreamingTurn) => {
      const id = activeIdRef.current;
      if (!id) return;
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? mut(t) : t)),
      );
    },
    [],
  );

  const ensureSocket = React.useCallback((): QueryWebSocket => {
    if (wsRef.current) return wsRef.current;
    const url = wsUrl ?? defaultWsUrl();
    const ws = new QueryWebSocket(
      {
        onToken: (delta) =>
          updateActive((t) => ({ ...t, answer: t.answer + delta })),
        onSources: (sources) => updateActive((t) => ({ ...t, sources })),
        onUsage: (usage) => updateActive((t) => ({ ...t, usage })),
        onMetadata: (metadata) =>
          updateActive((t) => ({ ...t, metadata })),
        onDone: () => {
          updateActive((t) => ({ ...t, status: "done" }));
          setIsStreaming(false);
          activeIdRef.current = null;
        },
        onError: (error) => {
          updateActive((t) => ({ ...t, status: "error", error }));
          setIsStreaming(false);
          activeIdRef.current = null;
        },
      },
      url,
    );
    wsRef.current = ws;
    ws.connect();
    return ws;
  }, [updateActive, wsUrl]);

  React.useEffect(() => {
    return () => {
      wsRef.current?.disconnect();
      wsRef.current = null;
    };
  }, []);

  const submit = React.useCallback(
    ({ question, collectionIds, reasoningEffort }: SubmitArgs) => {
      if (isStreaming) return;
      if (!question.trim() || collectionIds.length === 0) return;

      const id = `turn-${Date.now()}`;
      activeIdRef.current = id;
      setTurns((prev) => [
        ...prev,
        {
          id,
          question,
          answer: "",
          sources: [],
          usage: null,
          metadata: null,
          status: "streaming",
          error: null,
        },
      ]);
      setIsStreaming(true);

      const ws = ensureSocket();
      const options: QueryOptions = { reasoning_effort: reasoningEffort };
      // Slight delay if the socket is still opening — the WS client's own
      // queueing isn't perfect, so we wait a beat on the first send.
      const tryFire = (attempts = 0) => {
        if (ws.isConnected) {
          ws.sendQuery(question, collectionIds, options);
        } else if (attempts < 20) {
          setTimeout(() => tryFire(attempts + 1), 100);
        } else {
          updateActive((t) => ({
            ...t,
            status: "error",
            error: "WebSocket failed to open",
          }));
          setIsStreaming(false);
          activeIdRef.current = null;
        }
      };
      tryFire();
    },
    [isStreaming, ensureSocket, updateActive],
  );

  const reset = React.useCallback(() => {
    setTurns([]);
    setIsStreaming(false);
    activeIdRef.current = null;
  }, []);

  return { turns, isStreaming, submit, reset };
}

function defaultWsUrl(): string {
  // Browser-only — never rendered server-side because the hook is "use client".
  if (typeof window === "undefined") return "ws://localhost:8000/ws/query";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  // The frontend usually runs on a different port (3000) than the backend
  // (8000). Same host, different port is the standard local dev setup and
  // also matches the `docker compose --profile full` exposed port mapping.
  return `${protocol}//${window.location.hostname}:8000/ws/query`;
}
