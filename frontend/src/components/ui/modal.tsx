"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

/**
 * Minimal modal dialog using the native <dialog> element. Avoids a
 * dependency on @radix-ui/react-dialog while still giving us focus trap,
 * Escape-to-close, and backdrop click-to-close.
 */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: ModalProps) {
  const dialogRef = React.useRef<HTMLDialogElement | null>(null);

  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const handleClose = React.useCallback(() => {
    onOpenChange(false);
  }, [onOpenChange]);

  // Backdrop click — the click target is the dialog itself when the backdrop
  // is clicked. Inner content stops propagation.
  const handleClick = React.useCallback(
    (event: React.MouseEvent<HTMLDialogElement>) => {
      if (event.target === dialogRef.current) {
        handleClose();
      }
    },
    [handleClose],
  );

  return (
    <dialog
      ref={dialogRef}
      onClose={handleClose}
      onClick={handleClick}
      className={cn(
        "rounded-lg border border-border bg-card text-card-foreground shadow-lg backdrop:bg-black/50 backdrop:backdrop-blur-sm",
        "p-0 max-w-lg w-[calc(100%-2rem)]",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-border">
        <div className="space-y-1">
          {title ? <h2 className="text-base font-semibold leading-none">{title}</h2> : null}
          {description ? (
            <p className="text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Close"
          onClick={handleClose}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="px-6 py-4">{children}</div>
      {footer ? (
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border">
          {footer}
        </div>
      ) : null}
    </dialog>
  );
}
