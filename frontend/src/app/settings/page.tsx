"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { useHealth, useServerSettings } from "@/hooks/use-settings";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DependencyStatus } from "@/lib/types";

export default function SettingsPage() {
  const settings = useServerSettings();
  const health = useHealth();

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Server-side configuration. Edit values in <code>.env</code> or{" "}
          <code>config.yaml</code> and restart the backend to change them.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Health</CardTitle>
        </CardHeader>
        <CardContent>
          {health.isLoading ? (
            <Skeleton className="h-16" />
          ) : health.isError || !health.data ? (
            <p className="text-sm text-destructive">
              Could not reach the backend health endpoint.
            </p>
          ) : (
            <dl className="grid gap-3 sm:grid-cols-3">
              <HealthCell label="Qdrant" value={health.data.qdrant} />
              <HealthCell label="Embeddings" value={health.data.embedding_provider} />
              <HealthCell label="LLM" value={health.data.llm_provider} />
            </dl>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Models</CardTitle>
        </CardHeader>
        <CardContent>
          {settings.isLoading ? (
            <Skeleton className="h-40" />
          ) : settings.isError || !settings.data ? (
            <p className="text-sm text-destructive">
              Could not load settings: {String(settings.error)}
            </p>
          ) : (
            <dl className="grid gap-y-3 gap-x-6 sm:grid-cols-2">
              <Field label="LLM provider" value={settings.data.llm_provider} />
              <Field label="LLM model" value={settings.data.llm_model} mono />
              <Field
                label="Enrichment model"
                value={settings.data.enrichment_llm_model ?? "(uses LLM model)"}
                mono
              />
              <Field
                label="Reasoning effort"
                value={
                  <Badge variant="secondary">{settings.data.reasoning_effort}</Badge>
                }
              />
              <Field
                label="Embedding provider"
                value={settings.data.embedding_provider}
              />
              <Field
                label="Embedding model"
                value={`${settings.data.embedding_model} (${settings.data.embedding_dimensions}d)`}
                mono
              />
              <Field
                label="Reranker"
                value={`${settings.data.reranker_provider} / ${settings.data.reranker_model}`}
                mono
              />
            </dl>
          )}
        </CardContent>
      </Card>

      {settings.data ? (
        <Card>
          <CardHeader>
            <CardTitle>Pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-y-3 gap-x-6 sm:grid-cols-2">
              <Field label="Parser" value={settings.data.parser} />
              <Field
                label="Contextual enrichment"
                value={
                  <Badge variant={settings.data.contextual_enrichment ? "success" : "muted"}>
                    {settings.data.contextual_enrichment ? "enabled" : "disabled"}
                  </Badge>
                }
              />
              <Field
                label="Chunk size / overlap"
                value={`${settings.data.chunk_size_tokens} / ${settings.data.chunk_overlap_tokens} tokens`}
              />
              <Field
                label="Hybrid search"
                value={
                  <Badge variant={settings.data.hybrid_search ? "success" : "muted"}>
                    {settings.data.hybrid_search ? "enabled" : "disabled"}
                  </Badge>
                }
              />
              <Field
                label="Top-k retrieval / rerank"
                value={`${settings.data.top_k_retrieval} → ${settings.data.top_k_rerank}`}
              />
              <Field
                label="Multi-query expansion"
                value={
                  <Badge variant={settings.data.multi_query ? "success" : "muted"}>
                    {settings.data.multi_query ? "enabled" : "disabled"}
                  </Badge>
                }
              />
              <Field
                label="Corrective RAG"
                value={
                  <Badge variant={settings.data.corrective_rag ? "success" : "muted"}>
                    {settings.data.corrective_rag ? "enabled" : "disabled"}
                  </Badge>
                }
              />
              <Field label="Context expansion" value={settings.data.context_expansion} />
              <Field
                label="Max context tokens"
                value={settings.data.max_context_tokens.toLocaleString()}
              />
            </dl>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className={mono ? "mt-0.5 font-mono text-sm" : "mt-0.5 text-sm"}>{value}</dd>
    </div>
  );
}

function HealthCell({ label, value }: { label: string; value: DependencyStatus }) {
  const ok = value.status === "ok";
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center gap-2">
        <Icon className={ok ? "h-4 w-4 text-emerald-500" : "h-4 w-4 text-destructive"} />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{value.message ?? "—"}</p>
    </div>
  );
}
