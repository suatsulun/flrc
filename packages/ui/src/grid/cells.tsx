import { LockIcon } from "lucide-react";
import { useState, type KeyboardEvent, type RefCallback } from "react";

import { Button } from "../components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/dialog";
import { cn } from "../lib/utils";

export type CellValue = number | string | null;

export type CellProps = {
  value: CellValue;
  dirty: boolean;
  /** The column belongs to another teacher — entry is allowed but flagged. */
  caution?: boolean;
  onCommit: (value: CellValue) => void;
  onNavKey?: (event: KeyboardEvent) => void;
  cellRef?: RefCallback<HTMLElement>;
  /** Accessible name, e.g. "Ada Yılmaz — Reading". */
  label?: string;
  /** Fill a grid column while preserving a comfortable minimum hit target. */
  fit?: boolean;
};

/**
 * Shared cell chrome. Kept flat and tight: in a grid of several hundred cells,
 * per-cell shadows and rounded corners are visual noise that slows scanning.
 */
const cellBase =
  "h-9 rounded-md border border-input bg-card text-sm transition-[background-color,border-color,box-shadow] outline-none hover:border-border-strong focus-visible:z-10 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/35";
const cautionClass = "border-dashed border-warning/70 bg-warning-surface/40";
const dirtyClass = "border-primary bg-accent font-semibold text-accent-foreground";

export function ScoreCell({
  value,
  dirty,
  caution,
  onCommit,
  onNavKey,
  cellRef,
  label,
  fit,
}: CellProps) {
  return (
    <input
      ref={cellRef}
      inputMode="numeric"
      aria-label={label ?? "score"}
      className={cn(
        cellBase,
        fit ? "w-full min-w-14 px-1.5 text-center tabular" : "w-16 px-1 text-center tabular",
        caution && cautionClass,
        dirty && dirtyClass,
      )}
      value={value === null ? "" : String(value)}
      onFocus={(event) => event.currentTarget.select()}
      onChange={(event) => {
        const next = event.target.value;
        if (next === "") onCommit(null);
        else if (/^\d{1,3}$/.test(next) && Number(next) <= 100) onCommit(Number(next));
      }}
      onKeyDown={onNavKey}
    />
  );
}

export const SCALE3_FACES = { 1: "🙁", 2: "😐", 3: "🙂" } as const;

/** Three-point scale with visible labels and optional faces for primary English. */
export function Scale3Cell({
  value,
  dirty,
  caution,
  onCommit,
  onNavKey,
  cellRef,
  label,
  levelLabels,
  fit,
  showFaces = true,
}: CellProps & { levelLabels: Record<1 | 2 | 3, string>; showFaces?: boolean }) {
  const current = value === 1 || value === 2 || value === 3 ? value : null;
  const cycle = () => onCommit(current === null ? 1 : current === 3 ? null : current + 1);

  return (
    <button
      type="button"
      ref={cellRef}
      aria-label={
        current && levelLabels
          ? `${label ?? ""}: ${levelLabels[current]}`.replace(/^: /, "")
          : label
      }
      title={current && levelLabels ? levelLabels[current] : undefined}
      className={cn(
        cellBase,
        "inline-flex h-auto min-h-10 items-center justify-center gap-1.5 px-2 py-2 text-center leading-snug whitespace-normal",
        fit ? "w-full min-w-14" : "w-36 max-w-full shrink-0",
        current ? "" : "text-sm text-muted-foreground",
        caution && cautionClass,
        dirty && dirtyClass,
      )}
      onClick={cycle}
      onKeyDown={(event) => {
        if (event.key === "1" || event.key === "2" || event.key === "3") {
          event.preventDefault();
          onCommit(Number(event.key));
          return;
        }
        if (event.key === "0" || event.key === "Backspace" || event.key === "Delete") {
          event.preventDefault();
          onCommit(null);
          return;
        }
        if (event.key === " ") {
          event.preventDefault();
          cycle();
          return;
        }
        onNavKey?.(event);
      }}
    >
      {current ? (
        <>
          {showFaces ? (
            <span aria-hidden="true" className="text-lg">
              {SCALE3_FACES[current]}
            </span>
          ) : null}
          <span>{levelLabels[current]}</span>
        </>
      ) : (
        "—"
      )}
    </button>
  );
}

export type TextCellEditorLabels = {
  title: string;
  description: string;
  placeholder: string;
  empty: string;
  done: string;
};

export function TextCell({
  value,
  dirty,
  caution,
  onCommit,
  onNavKey,
  cellRef,
  label,
  fit,
  editorLabels,
}: CellProps & { editorLabels: TextCellEditorLabels }) {
  const text = typeof value === "string" ? value : "";
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(text);

  const openEditor = () => {
    setDraft(text);
    setOpen(true);
  };

  const finishEditing = () => {
    const trimmed = draft.trim();
    onCommit(trimmed === "" ? null : trimmed);
    setDraft(trimmed);
    setOpen(false);
  };

  return (
    <>
      <button
        ref={cellRef}
        type="button"
        aria-label={label ?? editorLabels.title}
        aria-haspopup="dialog"
        title={text || editorLabels.empty}
        className={cn(
          cellBase,
          "block truncate text-left",
          fit ? "w-full min-w-32 px-2" : "w-44 px-2",
          !text && "text-muted-foreground",
          caution && cautionClass,
          dirty && dirtyClass,
        )}
        onClick={openEditor}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") onNavKey?.(event);
        }}
      >
        {text || editorLabels.empty}
      </button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (next) openEditor();
          else finishEditing();
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editorLabels.title}</DialogTitle>
            <DialogDescription>{editorLabels.description}</DialogDescription>
          </DialogHeader>

          <textarea
            autoFocus
            aria-label={editorLabels.title}
            className="min-h-64 w-full resize-y rounded-xl border border-input bg-background px-4 py-3 text-base leading-6 shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-primary/15"
            maxLength={2000}
            placeholder={editorLabels.placeholder}
            value={draft}
            onChange={(event) => {
              const next = event.currentTarget.value;
              setDraft(next);
              onCommit(next === "" ? null : next);
            }}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                finishEditing();
              }
            }}
          />

          <p className="text-right text-xs tabular-nums text-muted-foreground">
            {draft.length} / 2000
          </p>

          <DialogFooter>
            <Button onClick={finishEditing}>{editorLabels.done}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function LockedCell({
  value,
  label,
  fit,
  wide,
  wrap,
}: {
  value: CellValue;
  label?: string;
  fit?: boolean;
  wide?: boolean;
  wrap?: boolean;
}) {
  return (
    <span
      aria-label={label}
      title={label}
      className={cn(
        "grid h-9 place-items-center rounded-md border border-border bg-muted/70 text-sm text-muted-foreground",
        fit ? "w-full min-w-14 px-1" : "w-16",
        wide && (fit ? "min-w-32 truncate px-2" : "w-44 truncate px-2"),
        wrap &&
          "h-auto min-h-10 max-w-full shrink-0 px-2 py-2 text-center leading-snug whitespace-normal",
        wrap && !fit && "w-36",
      )}
    >
      {value ?? <LockIcon className="size-3.5" />}
    </span>
  );
}
