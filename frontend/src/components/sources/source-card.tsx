"use client";

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { SourceResponse } from "@/lib/types";

interface SourceCardProps {
  index: number;
  source: SourceResponse;
}

export function SourceCard({ index, source }: SourceCardProps) {
  const [open, setOpen] = React.useState(false);

  return (
    <Card className="bg-muted/30">
      <CardContent className="p-3">
        <button
          type="button"
          className="flex w-full items-start gap-2 text-left"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="mt-0.5 text-muted-foreground">
            {open ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-xs font-mono text-muted-foreground">[{index}]</span>
              <span className="text-sm font-medium truncate">{source.filename}</span>
              {source.page_numbers.length > 0 ? (
                <span className="text-xs text-muted-foreground">
                  p. {source.page_numbers.join(", ")}
                </span>
              ) : null}
              <Badge variant="secondary" className="ml-auto">
                {source.relevance_score.toFixed(3)}
              </Badge>
            </div>
            {source.header_chain.length > 0 ? (
              <p className="mt-0.5 text-xs text-muted-foreground truncate">
                {source.header_chain.join(" › ")}
              </p>
            ) : null}
          </div>
        </button>
        <div
          className={cn(
            "overflow-hidden transition-[max-height] duration-150 ease-out",
            open ? "max-h-[24rem]" : "max-h-0",
          )}
        >
          <pre className="mt-2 max-h-[22rem] overflow-y-auto whitespace-pre-wrap rounded-md bg-background p-3 text-xs leading-relaxed">
            {source.chunk_text}
          </pre>
        </div>
      </CardContent>
    </Card>
  );
}
