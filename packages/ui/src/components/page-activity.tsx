import { Skeleton } from "#components/skeleton";
import { cn } from "#lib/utils";

/**
 * The page's one polite "Loading…" announcement while its first data loads. Sighted
 * users see the page's skeleton instead, so the status itself stays visually hidden.
 * It is always mounted: a live region that exists before its text changes is announced
 * reliably.
 */
function PageActivity({ active, label }: { active: boolean; label: string }) {
  return (
    <p role="status" className="sr-only">
      {active ? label : null}
    </p>
  );
}

/** A loading announcement for a skeleton shown where no `PageActivity` is listening. */
function LoadingStatus({ label }: { label: string }) {
  return (
    <p role="status" className="sr-only">
      {label}
    </p>
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

export { LoadingStatus, PageActivity, PageSkeleton };
