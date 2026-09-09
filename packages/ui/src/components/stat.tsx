import type { ReactNode } from "react";

import { cn } from "#lib/utils";

/**
 * One number and what it means. Kept quiet on purpose: these appear in rows of
 * four to six, and a row of loud tiles is a row nobody reads.
 */
export function Stat({
  value,
  label,
  tone = "default",
  className,
}: {
  value: ReactNode;
  label: ReactNode;
  tone?: "default" | "success" | "warning" | "danger";
  className?: string;
}) {
  const valueTone = {
    default: "text-foreground",
    success: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
  }[tone];

  return (
    <div className={cn("rounded-lg border border-border bg-card px-4 py-3 shadow-card", className)}>
      <div className={cn("tabular font-heading text-2xl font-semibold tracking-tight", valueTone)}>
        {value}
      </div>
      <div className="mt-0.5 truncate text-xs text-muted-foreground" title={String(label)}>
        {label}
      </div>
    </div>
  );
}

/** Horizontal rule of stats that wraps predictably. */
export function StatRow({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("grid gap-3 sm:grid-cols-3 lg:grid-cols-6", className)}>{children}</div>
  );
}
