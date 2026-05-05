"use client";

import * as React from "react";
import { useCollections } from "@/hooks/use-collections";
import { useDocuments } from "@/hooks/use-documents";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentRow } from "@/components/documents/document-row";
import { UploadForm } from "@/components/documents/upload-form";

export default function DocumentsPage() {
  const collections = useCollections();
  const [collectionId, setCollectionId] = React.useState<string>("");

  // Auto-select the first collection once they load.
  React.useEffect(() => {
    if (
      collectionId === "" &&
      collections.data &&
      collections.data.length > 0
    ) {
      setCollectionId(collections.data[0].id);
    }
  }, [collectionId, collections.data]);

  const documents = useDocuments(collectionId || null);
  const collection = collections.data?.find((c) => c.id === collectionId);

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload PDFs into a collection. Ingestion timing and status are
            recorded per document.
          </p>
        </div>
        <div className="space-y-1.5 min-w-[12rem]">
          <Label htmlFor="collection-picker">Collection</Label>
          <Select
            id="collection-picker"
            value={collectionId}
            onChange={(e) => setCollectionId(e.target.value)}
            disabled={collections.isLoading}
          >
            <option value="">— select —</option>
            {collections.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </div>
      </header>

      {collections.data && collections.data.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            No collections yet. Create one on the{" "}
            <a className="underline" href="/collections">
              Collections page
            </a>{" "}
            first.
          </CardContent>
        </Card>
      ) : null}

      {collection ? (
        <UploadForm
          collectionId={collection.id}
          collectionName={collection.name}
        />
      ) : null}

      <Card>
        <CardContent className="p-0">
          {!collectionId ? (
            <p className="p-6 text-sm text-muted-foreground">
              Select a collection to view its documents.
            </p>
          ) : documents.isLoading ? (
            <div className="p-6 space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : documents.isError ? (
            <p className="p-6 text-sm text-destructive">
              Failed to load documents: {String(documents.error)}
            </p>
          ) : !documents.data || documents.data.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              No documents in this collection yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border">
                    <th className="py-3 pr-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Filename
                    </th>
                    <th className="py-3 pr-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Status
                    </th>
                    <th className="py-3 pr-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Role
                    </th>
                    <th className="py-3 pr-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Ingest time
                    </th>
                    <th className="py-3 pr-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Chunks
                    </th>
                    <th className="py-3 pr-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Size
                    </th>
                    <th className="py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {documents.data.map((doc) => (
                    <DocumentRow key={doc.id} document={doc} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
