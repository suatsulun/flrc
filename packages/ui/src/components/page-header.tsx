import type { ReactNode } from "react";

import { cn } from "#lib/utils";

/**
 * The first thing on every page: what this screen is, and its primary actions.
 *
 * Deliberately flat — no card, no gradient. The page's own content should be the
 * thing that draws the eye.
 */
export function PageHeader({
  title,
  description,
  actions,
  meta,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  /** Buttons and controls, right-aligned on desktop. */
  actions?: ReactNode;
  /** Small status line under the title — counts, scope, read-only notices. */
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-4", className)}>
      <div className="min-w-0">
        <h1 className="font-heading text-xl font-semibold tracking-tight text-balance">{title}</h1>
        {description ? (
          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p>
        ) : null}
        {meta ? <div className="mt-2 flex flex-wrap items-center gap-2">{meta}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
