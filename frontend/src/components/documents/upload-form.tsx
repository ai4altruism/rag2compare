"use client";

import * as React from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useUploadDocuments } from "@/hooks/use-documents";

const ROLE_OPTIONS = [
  "",
  "Anchor",
  "Chrono",
  "Bridge",
  "Conflict",
  "Technical Bridge",
  "Meta Bridge",
  "Chrono/Anchor",
  "Chrono/Baseline",
] as const;

interface UploadFormProps {
  collectionId: string;
  collectionName: string;
}

export function UploadForm({ collectionId, collectionName }: UploadFormProps) {
  const upload = useUploadDocuments();
  const [files, setFiles] = React.useState<File[]>([]);
  const [domain, setDomain] = React.useState(collectionName);
  const [role, setRole] = React.useState<string>("");
  const [year, setYear] = React.useState<string>("");
  const [authors, setAuthors] = React.useState<string>("");
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    setDomain(collectionName);
  }, [collectionName]);

  const tags = React.useMemo<Record<string, unknown>>(() => {
    const out: Record<string, unknown> = {};
    if (domain) out.domain = domain;
    if (role) out.role = role;
    if (year) {
      const n = Number(year);
      out.year = Number.isFinite(n) ? n : year;
    }
    if (authors) out.authors = authors;
    return out;
  }, [domain, role, year, authors]);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (files.length === 0) return;
    await upload.mutateAsync({
      collectionId,
      files,
      tags: Object.keys(tags).length > 0 ? tags : null,
    });
    setFiles([]);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload PDFs</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="upload-files">PDF files</Label>
            <Input
              id="upload-files"
              ref={inputRef}
              type="file"
              multiple
              accept="application/pdf,.pdf"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            {files.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                {files.length} file{files.length === 1 ? "" : "s"} selected
              </p>
            ) : null}
          </div>

          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="text-xs uppercase tracking-wider text-muted-foreground sm:col-span-2">
              Tags (applied to every uploaded file)
            </legend>
            <div className="space-y-1.5">
              <Label htmlFor="upload-domain">Domain</Label>
              <Input
                id="upload-domain"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="ai-ethics-law"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="upload-role">Role</Label>
              <Select
                id="upload-role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r === "" ? "(none)" : r}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="upload-year">Year</Label>
              <Input
                id="upload-year"
                type="number"
                value={year}
                onChange={(e) => setYear(e.target.value)}
                placeholder="2026"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="upload-authors">Authors</Label>
              <Input
                id="upload-authors"
                value={authors}
                onChange={(e) => setAuthors(e.target.value)}
                placeholder="Stober & Dornis"
              />
            </div>
          </fieldset>

          {upload.error ? (
            <p className="text-xs text-destructive">{String(upload.error)}</p>
          ) : null}

          <div className="flex justify-end">
            <Button type="submit" disabled={files.length === 0 || upload.isPending}>
              <Upload className="h-4 w-4" />
              {upload.isPending ? "Uploading…" : "Upload"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
