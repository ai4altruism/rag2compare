"use client";

import * as React from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import {
  useDeleteDocument,
  useReingestDocument,
} from "@/hooks/use-documents";
import type { DocumentResponse } from "@/lib/types";

const STATUS_VARIANTS: Record<
  string,
  "default" | "secondary" | "destructive" | "success" | "warning" | "muted"
> = {
  completed: "success",
  error: "destructive",
  failed: "destructive",
  pending: "muted",
  parsing: "warning",
  chunking: "warning",
  enriching: "warning",
  embedding: "warning",
  storing: "warning",
  processing: "warning",
};

function formatSeconds(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(1)}s`;
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "—";
  const mb = bytes / 1024 / 1024;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

interface DocumentRowProps {
  document: DocumentResponse;
}

export function DocumentRow({ document }: DocumentRowProps) {
  const reingest = useReingestDocument();
  const remove = useDeleteDocument();
  const [confirming, setConfirming] = React.useState(false);

  const role = document.tags?.role as string | undefined;
  const variant = STATUS_VARIANTS[document.status] ?? "muted";

  return (
    <tr className="border-b border-border last:border-b-0">
      <td className="py-3 pr-4 text-sm font-medium align-top">
        <div className="flex flex-col">
          <span>{document.filename}</span>
          {document.error_message ? (
            <span className="mt-1 text-xs text-destructive">
              {document.error_message}
            </span>
          ) : null}
        </div>
      </td>
      <td className="py-3 pr-4 align-top">
        <Badge variant={variant}>{document.status}</Badge>
      </td>
      <td className="py-3 pr-4 align-top text-sm">
        {role ? <Badge variant="outline">{role}</Badge> : <span className="text-muted-foreground">—</span>}
      </td>
      <td className="py-3 pr-4 align-top text-sm tabular-nums">
        {formatSeconds(document.ingestion_seconds)}
      </td>
      <td className="py-3 pr-4 align-top text-sm tabular-nums">
        {document.chunk_count ?? "—"}
      </td>
      <td className="py-3 pr-4 align-top text-sm tabular-nums text-muted-foreground">
        {formatBytes(document.file_size_bytes)}
      </td>
      <td className="py-3 align-top">
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Re-ingest ${document.filename}`}
            disabled={reingest.isPending}
            onClick={() => reingest.mutate({ id: document.id })}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Delete ${document.filename}`}
            onClick={() => setConfirming(true)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
        <Modal
          open={confirming}
          onOpenChange={setConfirming}
          title={`Delete "${document.filename}"?`}
          description="The document and its vectors will be removed permanently."
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                disabled={remove.isPending}
                onClick={async () => {
                  await remove.mutateAsync(document.id);
                  setConfirming(false);
                }}
              >
                {remove.isPending ? "Deleting…" : "Delete"}
              </Button>
            </>
          }
        />
      </td>
    </tr>
  );
}
