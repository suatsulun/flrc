import { PaperclipIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "#lib/utils";

/**
 * A native file input with a localized face.
 *
 * The browser draws its own "Choose file / No file chosen" text in the browser's language, not the
 * app's. The real input stays in place, transparent and on top: it keeps the `Field` label, the
 * keyboard focus, the native picker and `setInputFiles` in tests, while the face below shows the
 * localized button text and the chosen file's name.
 */
function FilePicker({
  className,
  chooseLabel,
  emptyLabel,
  fileName,
  ...props
}: Omit<ComponentProps<"input">, "type"> & {
  chooseLabel: string;
  emptyLabel: string;
  /** Name of the chosen file; the face shows `emptyLabel` without one. */
  fileName?: string;
}) {
  return (
    <span data-slot="file-picker" className={cn("relative flex h-9 w-full min-w-0", className)}>
      <input
        type="file"
        className="peer absolute inset-0 z-10 size-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        {...props}
      />
      <span
        aria-hidden
        className={cn(
          "flex w-full min-w-0 items-center overflow-hidden rounded-lg border border-input bg-card text-sm shadow-card transition-colors",
          "peer-hover:border-border-strong peer-focus-visible:border-primary peer-focus-visible:ring-3 peer-focus-visible:ring-ring/25",
          "peer-disabled:opacity-50",
        )}
      >
        <span className="flex h-full shrink-0 items-center gap-1.5 border-r border-input bg-muted px-3 font-medium">
          <PaperclipIcon className="size-3.5" />
          {chooseLabel}
        </span>
        <span
          className={cn("min-w-0 truncate px-3", fileName ? "" : "text-muted-foreground")}
          title={fileName}
        >
          {fileName ?? emptyLabel}
        </span>
      </span>
    </span>
  );
}

export { FilePicker };
