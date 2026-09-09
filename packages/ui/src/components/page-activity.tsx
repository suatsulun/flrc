import { LoaderCircleIcon } from "lucide-react";

import { Skeleton } from "#components/skeleton";
import { cn } from "#lib/utils";

/** A persistent, non-blocking signal for a page's first data request. */
function PageActivity({ active, label }: { active: boolean; label: string }) {
  if (!active) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed top-[calc(var(--app-shell-header-height)+0.75rem)] left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs font-medium text-popover-foreground shadow-raised backdrop-blur"
    >
      <LoaderCircleIcon className="size-3.5 animate-spin text-primary" />
      <span>{label}</span>
    </div>
  );
}

/** Stable page-shaped fallback used before a route's first query resolves. */
function PageSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-5", className)} aria-hidden>
      <div className="space-y-2">
        <Skeleton className="h-7 w-56 max-w-2/3" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <Skeleton className="h-12 w-full rounded-xl" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Skeleton className="h-36" />
        <Skeleton className="h-36" />
        <Skeleton className="h-36" />
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function FullScreenLoading({ label }: { label: string }) {
  return (
    <main className="grid min-h-svh place-items-center bg-background" role="status">
      <span className="flex items-center gap-3 rounded-full border border-border bg-popover px-4 py-2 text-sm font-medium shadow-raised">
        <LoaderCircleIcon className="size-4 animate-spin text-primary" />
        {label}
      </span>
    </main>
  );
}

export { FullScreenLoading, PageActivity, PageSkeleton };
