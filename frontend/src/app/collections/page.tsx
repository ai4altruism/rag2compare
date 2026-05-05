"use client";

import * as React from "react";
import { Plus, Trash2, Pencil } from "lucide-react";
import {
  useCollections,
  useCreateCollection,
  useDeleteCollection,
  useUpdateCollection,
} from "@/hooks/use-collections";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { CollectionResponse } from "@/lib/types";

export default function CollectionsPage() {
  const collections = useCollections();
  const createMutation = useCreateCollection();
  const updateMutation = useUpdateCollection();
  const deleteMutation = useDeleteCollection();

  const [createOpen, setCreateOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<CollectionResponse | null>(null);
  const [confirmingDelete, setConfirmingDelete] =
    React.useState<CollectionResponse | null>(null);

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Collections</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Group ingested documents. Queries can span one or many collections.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          New collection
        </Button>
      </header>

      {collections.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : collections.isError ? (
        <Card className="border-destructive/40">
          <CardContent className="pt-6 text-sm text-destructive">
            Failed to load collections: {String(collections.error)}
          </CardContent>
        </Card>
      ) : collections.data && collections.data.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {collections.data.map((c) => (
            <Card key={c.id}>
              <CardHeader className="flex flex-row items-start justify-between space-y-0 gap-2">
                <div className="space-y-1">
                  <CardTitle>{c.name}</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    {c.document_count} document{c.document_count === 1 ? "" : "s"} ·{" "}
                    Created {new Date(c.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Edit ${c.name}`}
                    onClick={() => setEditing(c)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete ${c.name}`}
                    onClick={() => setConfirmingDelete(c)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              {c.description ? (
                <CardContent className="text-sm text-muted-foreground whitespace-pre-line">
                  {c.description}
                </CardContent>
              ) : null}
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            No collections yet. Create one to get started.
          </CardContent>
        </Card>
      )}

      <CreateCollectionModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={async (data) => {
          await createMutation.mutateAsync(data);
          setCreateOpen(false);
        }}
        isPending={createMutation.isPending}
        error={createMutation.error ? String(createMutation.error) : null}
      />

      <EditCollectionModal
        collection={editing}
        onClose={() => setEditing(null)}
        onSave={async (id, data) => {
          await updateMutation.mutateAsync({ id, data });
          setEditing(null);
        }}
        isPending={updateMutation.isPending}
        error={updateMutation.error ? String(updateMutation.error) : null}
      />

      <Modal
        open={confirmingDelete !== null}
        onOpenChange={(open) => !open && setConfirmingDelete(null)}
        title={`Delete "${confirmingDelete?.name ?? ""}"?`}
        description="This deletes the collection and removes its vectors from Qdrant. Documents will need to be re-uploaded."
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirmingDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={async () => {
                if (!confirmingDelete) return;
                await deleteMutation.mutateAsync(confirmingDelete.id);
                setConfirmingDelete(null);
              }}
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete"}
            </Button>
          </>
        }
      />
    </div>
  );
}

interface CreateModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (data: { name: string; description?: string | null }) => Promise<void>;
  isPending: boolean;
  error: string | null;
}

function CreateCollectionModal({
  open,
  onOpenChange,
  onCreate,
  isPending,
  error,
}: CreateModalProps) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
    }
  }, [open]);

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="New collection"
      description="A collection groups documents that should be queried together."
      footer={
        <>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!name.trim() || isPending}
            onClick={() =>
              onCreate({
                name: name.trim(),
                description: description.trim() || null,
              })
            }
          >
            {isPending ? "Creating…" : "Create"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="new-collection-name">Name</Label>
          <Input
            id="new-collection-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ai-ethics-law"
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="new-collection-desc">Description (optional)</Label>
          <Textarea
            id="new-collection-desc"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
      </div>
    </Modal>
  );
}

interface EditModalProps {
  collection: CollectionResponse | null;
  onClose: () => void;
  onSave: (id: string, data: { name?: string; description?: string | null }) => Promise<void>;
  isPending: boolean;
  error: string | null;
}

function EditCollectionModal({
  collection,
  onClose,
  onSave,
  isPending,
  error,
}: EditModalProps) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");

  React.useEffect(() => {
    if (collection) {
      setName(collection.name);
      setDescription(collection.description ?? "");
    }
  }, [collection]);

  return (
    <Modal
      open={collection !== null}
      onOpenChange={(open) => !open && onClose()}
      title={collection ? `Edit "${collection.name}"` : ""}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!collection || !name.trim() || isPending}
            onClick={() => {
              if (!collection) return;
              return onSave(collection.id, {
                name: name.trim(),
                description: description.trim() || null,
              });
            }}
          >
            {isPending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="edit-collection-name">Name</Label>
          <Input
            id="edit-collection-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="edit-collection-desc">Description</Label>
          <Textarea
            id="edit-collection-desc"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
      </div>
    </Modal>
  );
}
