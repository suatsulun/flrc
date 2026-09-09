import type { ComponentProps } from "react";

import { cn } from "#lib/utils";

/** Placeholder block shown while a query is in flight. */
function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div aria-hidden className={cn("animate-pulse rounded-lg bg-muted", className)} {...props} />
  );
}

/** A few skeleton rows sized like a table body, to stop layout jumping. */
function SkeletonRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2 p-4", className)}>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-9" />
      ))}
    </div>
  );
}

export { Skeleton, SkeletonRows };
