"use client";

import * as React from "react";
import { Send } from "lucide-react";
import { useCollections } from "@/hooks/use-collections";
import { useServerSettings } from "@/hooks/use-settings";
import { useStreamQuery, type StreamingTurn } from "@/hooks/use-stream-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { SourceCard } from "@/components/sources/source-card";
import type { ReasoningEffort } from "@/lib/types";

const REASONING_OPTIONS: ReasoningEffort[] = [
  "off",
  "low",
  "medium",
  "high",
  "xhigh",
];

export default function ChatPage() {
  const collections = useCollections();
  const settings = useServerSettings();
  const { turns, isStreaming, submit, reset } = useStreamQuery();

  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [reasoningEffort, setReasoningEffort] =
    React.useState<ReasoningEffort | "">("");
  const [question, setQuestion] = React.useState("");
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

  // Default the reasoning-effort selector to whatever the server is configured for.
  React.useEffect(() => {
    if (
      settings.data?.reasoning_effort &&
      reasoningEffort === ""
    ) {
      setReasoningEffort(settings.data.reasoning_effort as ReasoningEffort);
    }
  }, [settings.data, reasoningEffort]);

  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  const toggleCollection = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (selected.size === 0 || !question.trim()) return;
    submit({
      question: question.trim(),
      collectionIds: Array.from(selected),
      reasoningEffort: (reasoningEffort || "xhigh") as ReasoningEffort,
    });
    setQuestion("");
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      const form = event.currentTarget.form;
      if (form) form.requestSubmit();
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-4 p-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Chat</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Ask grounded questions across one or more collections. Answers
            stream in with cited sources.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {settings.data ? (
            <Badge variant="outline">{settings.data.llm_model}</Badge>
          ) : null}
          <Button variant="ghost" size="sm" onClick={reset} disabled={turns.length === 0}>
            Clear thread
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Query setup</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Collections
            </Label>
            {collections.isLoading ? (
              <div className="mt-2 flex gap-2">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-7 w-32" />
                ))}
              </div>
            ) : !collections.data || collections.data.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">
                No collections yet — create one on the Collections page.
              </p>
            ) : (
              <div className="mt-2 flex flex-wrap gap-2">
                {collections.data.map((c) => {
                  const active = selected.has(c.id);
                  return (
                    <button
                      type="button"
                      key={c.id}
                      onClick={() => toggleCollection(c.id)}
                      aria-pressed={active}
                      className={
                        "inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors " +
                        (active
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-background hover:bg-accent border-input")
                      }
                    >
                      {c.name}
                      <span className="opacity-70">({c.document_count})</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <div className="flex items-end gap-3 flex-wrap">
            <div className="space-y-1.5 min-w-[10rem]">
              <Label htmlFor="reasoning-effort" className="text-xs uppercase tracking-wider text-muted-foreground">
                Reasoning effort
              </Label>
              <Select
                id="reasoning-effort"
                value={reasoningEffort}
                onChange={(e) =>
                  setReasoningEffort(e.target.value as ReasoningEffort)
                }
              >
                {REASONING_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      <div ref={scrollRef} className="flex-1 overflow-y-auto rounded-md">
        {turns.length === 0 ? (
          <div className="flex h-full min-h-[12rem] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <p>Pick one or more collections, then ask a question.</p>
            <p className="text-xs">⌘/Ctrl + Enter to submit.</p>
          </div>
        ) : (
          <div className="space-y-6 pb-4">
            {turns.map((turn) => (
              <Turn key={turn.id} turn={turn} />
            ))}
          </div>
        )}
      </div>

      <form onSubmit={onSubmit} className="space-y-2">
        <Textarea
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="What's the relationship between G-Drift MIA and the Liang & Lut counterfactual infringement criterion?"
          disabled={isStreaming}
        />
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {selected.size === 0
              ? "Select at least one collection."
              : `${selected.size} collection${selected.size === 1 ? "" : "s"} selected`}
          </span>
          <Button
            type="submit"
            disabled={
              isStreaming ||
              selected.size === 0 ||
              !question.trim() ||
              !collections.data ||
              collections.data.length === 0
            }
          >
            <Send className="h-4 w-4" />
            {isStreaming ? "Streaming…" : "Send"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function Turn({ turn }: { turn: StreamingTurn }) {
  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="p-4">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            You
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm">{turn.question}</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Assistant
            </p>
            {turn.status === "streaming" ? (
              <Badge variant="warning">streaming…</Badge>
            ) : turn.status === "error" ? (
              <Badge variant="destructive">error</Badge>
            ) : null}
          </div>
          {turn.error ? (
            <p className="mt-2 text-sm text-destructive">{turn.error}</p>
          ) : (
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
              {turn.answer || (turn.status === "streaming" ? "…" : "")}
            </p>
          )}

          {turn.metadata ? (
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <Badge variant="muted">
                {turn.metadata.latency_ms}ms
              </Badge>
              {turn.metadata.reasoning_effort ? (
                <Badge variant="muted">
                  effort: {turn.metadata.reasoning_effort}
                </Badge>
              ) : null}
              {turn.usage?.prompt_tokens != null ? (
                <Badge variant="muted">
                  prompt: {turn.usage.prompt_tokens.toLocaleString()}
                </Badge>
              ) : null}
              {turn.usage?.completion_tokens != null ? (
                <Badge variant="muted">
                  completion: {turn.usage.completion_tokens.toLocaleString()}
                </Badge>
              ) : null}
              {turn.usage?.thinking_tokens != null ? (
                <Badge variant="muted">
                  thinking: {turn.usage.thinking_tokens.toLocaleString()}
                </Badge>
              ) : null}
              <Badge variant="muted">
                retrieved: {turn.metadata.retrieval_count} → {turn.metadata.reranked_count}
              </Badge>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {turn.sources.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Sources
          </p>
          <div className="space-y-2">
            {turn.sources.map((s, i) => (
              <SourceCard key={`${turn.id}-${i}`} index={i + 1} source={s} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
