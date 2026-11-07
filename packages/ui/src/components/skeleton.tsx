import type { ComponentProps, ReactNode } from "react";

import { Card, CardBody, CardHeader } from "#components/card";
import { cn } from "#lib/utils";

/*
 * Layout-shaped placeholders shown while a page or region loads its first data.
 *
 * Every block here is `aria-hidden`: a skeleton has nothing to say to a screen reader.
 * The page announces "Loading…" once, through one polite status (`PageActivity` inside
 * the shell, `LoadingStatus` where no shell status exists, e.g. a modal dialog). The pulse
 * stops for people who ask for reduced motion.
 */

/**
 * Placeholder block shown while a query is in flight. The muted surface is nudged towards the
 * text colour so blocks stay visible on the page background, on cards and in table headers in
 * both themes.
 */
function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      className={cn(
        "animate-pulse rounded-lg bg-[color-mix(in_oklch,var(--muted),var(--foreground)_14%)] motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  );
}

/** Varied bar widths, so rows of placeholders do not read as a solid block. */
const WIDTHS = ["w-4/5", "w-3/5", "w-2/3", "w-1/2", "w-3/4"] as const;
const width = (index: number) => WIDTHS[index % WIDTHS.length];
const times = (count: number) => Array.from({ length: count }, (_, index) => index);

/** A few skeleton rows sized like a table body, to stop layout jumping. */
function SkeletonRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div aria-hidden className={cn("space-y-2 p-4", className)}>
      {times(rows).map((index) => (
        <Skeleton key={index} className="h-9" />
      ))}
    </div>
  );
}

/** Lines of text; a paragraph's last line ends short. */
function SkeletonText({ lines = 2, className }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden className={cn("space-y-2", className)}>
      {times(lines).map((index) => (
        <Skeleton
          key={index}
          className={cn("h-3.5 rounded-md", lines > 1 && index === lines - 1 ? "w-3/5" : "w-full")}
        />
      ))}
    </div>
  );
}

/** `PageHeader`'s shape: title, description, an optional meta badge and actions. */
function SkeletonPageHeader({
  actions = 0,
  meta = false,
  className,
}: {
  actions?: number;
  meta?: boolean;
  className?: string;
}) {
  return (
    <div
      aria-hidden
      className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-4", className)}
    >
      <div className="min-w-0 flex-1 space-y-2.5">
        <Skeleton className="h-7 w-56 max-w-2/3" />
        <Skeleton className="h-4 w-full max-w-md" />
        {meta ? <Skeleton className="h-5 w-24 rounded-full" /> : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">
          {times(actions).map((index) => (
            <Skeleton key={index} className="h-9 w-28" />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** `StatRow`'s shape: quiet number tiles. */
function SkeletonStatRow({ count = 6, className }: { count?: number; className?: string }) {
  return (
    <div aria-hidden className={cn("grid gap-3 sm:grid-cols-3 lg:grid-cols-6", className)}>
      {times(count).map((index) => (
        <div key={index} className="rounded-lg border border-border bg-card px-4 py-3 shadow-card">
          <Skeleton className="h-7 w-12" />
          <Skeleton className="mt-1.5 h-3 w-20 max-w-full rounded-md" />
        </div>
      ))}
    </div>
  );
}

/** A card with a title (and description, header action) above whatever placeholder body it holds. */
function SkeletonCard({
  description = true,
  action = false,
  className,
  children,
}: {
  description?: boolean;
  /** A header button or badge on the right. */
  action?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <Card aria-hidden className={className}>
      <CardHeader className={children ? "border-b border-border" : undefined}>
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-4 w-40 max-w-2/3 rounded-md" />
          {description ? <Skeleton className="h-3.5 w-72 max-w-full rounded-md" /> : null}
        </div>
        {action ? <Skeleton className="h-8 w-24" /> : null}
      </CardHeader>
      {children ? <CardBody>{children}</CardBody> : null}
    </Card>
  );
}

/** A table's shape — header row and body rows — for a region whose table has not loaded yet. */
function SkeletonTable({
  columns = 4,
  rows = 6,
  className,
}: {
  columns?: number;
  rows?: number;
  className?: string;
}) {
  // The first column holds names and is the widest, as in the app's tables.
  const template = { gridTemplateColumns: `minmax(0,1.6fr) repeat(${columns - 1}, minmax(0,1fr))` };
  return (
    <div aria-hidden className={cn("w-full min-w-0 overflow-hidden text-sm", className)}>
      <div className="grid border-b border-border bg-muted/85" style={template}>
        {times(columns).map((column) => (
          <div key={column} className="px-3 py-3">
            <Skeleton className="h-3 w-16 max-w-full rounded-md bg-muted-foreground/15" />
          </div>
        ))}
      </div>
      {times(rows).map((row) => (
        <div
          key={row}
          className="grid border-b border-border/70 even:bg-muted/20 last:border-b-0"
          style={template}
        >
          {times(columns).map((column) => (
            <div key={column} className="px-3 py-3">
              <Skeleton className={cn("h-4 rounded-md", width(row + column))} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

/** Placeholder rows inside an existing `<tbody>`: first load or the next page of a long list. */
function SkeletonTableRows({ columns, rows = 3 }: { columns: number; rows?: number }) {
  return (
    <>
      {times(rows).map((row) => (
        <tr key={row} aria-hidden>
          {times(columns).map((column) => (
            <td key={column} className="border-b border-border/70 px-3 py-3">
              <Skeleton className={cn("h-4 rounded-md", width(row + column))} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

/** Labelled form controls; the caller lays them out (`grid-cols-…`). */
function SkeletonFields({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div aria-hidden className={cn("grid gap-3", className)}>
      {times(count).map((index) => (
        <div key={index} className="grid gap-1.5">
          <Skeleton className="h-3.5 w-24 rounded-md" />
          <Skeleton className="h-9 w-full" />
        </div>
      ))}
    </div>
  );
}

/** Rows of a divided list: an optional icon, a title over a detail line, an optional action. */
function SkeletonList({
  rows = 4,
  icon = false,
  action = false,
  className,
}: {
  rows?: number;
  icon?: boolean;
  action?: boolean;
  className?: string;
}) {
  return (
    <div aria-hidden className={cn("divide-y divide-border", className)}>
      {times(rows).map((row) => (
        <div key={row} className="flex items-center gap-3 px-5 py-3">
          {icon ? <Skeleton className="size-8 shrink-0" /> : null}
          <div className="min-w-0 flex-1 space-y-1.5">
            <Skeleton className={cn("h-4 rounded-md", width(row))} />
            <Skeleton className="h-3 w-1/3 rounded-md" />
          </div>
          {action ? <Skeleton className="h-8 w-20 shrink-0" /> : null}
        </div>
      ))}
    </div>
  );
}

/** `Segmented`'s shape: a row of tabs or choices. */
function SkeletonTabs({
  count = 4,
  size = "default",
  className,
}: {
  count?: number;
  size?: "sm" | "default";
  className?: string;
}) {
  return (
    <div
      aria-hidden
      className={cn(
        "inline-flex max-w-full flex-wrap items-center gap-0.5 rounded-lg border border-border bg-muted/60 p-0.5",
        className,
      )}
    >
      {times(count).map((index) => (
        <Skeleton
          key={index}
          className={cn(
            "rounded-[0.3rem] bg-muted-foreground/15",
            size === "sm" ? "h-6 w-14" : "h-7 w-16",
          )}
        />
      ))}
    </div>
  );
}

/** A slim bar of controls in a card, like `AcademicContextBar` or a filter bar. */
function SkeletonToolbar({ controls = 3, className }: { controls?: number; className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-2.5 py-2 shadow-card",
        className,
      )}
    >
      {times(controls).map((index) => (
        <Skeleton key={index} className={cn("h-8", index === 0 ? "w-24" : "w-36")} />
      ))}
    </div>
  );
}

/**
 * The teacher grade grid's shape: the assessment filter above a table with the student
 * column pinned left and one input box per assessment.
 */
function SkeletonGrid({
  columns = 4,
  rows = 8,
  className,
}: {
  columns?: number;
  rows?: number;
  className?: string;
}) {
  const template = { gridTemplateColumns: `184px repeat(${columns}, minmax(0,1fr))` };
  return (
    <div
      aria-hidden
      className={cn(
        "w-full min-w-0 overflow-hidden rounded-xl border border-border bg-card shadow-card",
        className,
      )}
    >
      <div className="space-y-3 border-b border-border p-3">
        <SkeletonTabs count={4} size="sm" />
        <Skeleton className="h-4 w-40 rounded-md" />
      </div>
      <div className="grid border-b border-border bg-muted" style={template}>
        {times(columns + 1).map((column) => (
          <div key={column} className="space-y-2 px-2 py-3">
            {column > 0 ? (
              <Skeleton className="h-3 w-12 rounded-md bg-muted-foreground/15" />
            ) : null}
            <Skeleton
              className={cn(
                "h-4 rounded-md bg-muted-foreground/15",
                column === 0 ? "w-20" : width(column),
              )}
            />
          </div>
        ))}
      </div>
      {times(rows).map((row) => (
        <div key={row} className="grid border-b border-border/60 even:bg-muted/25" style={template}>
          <div className="space-y-1.5 px-2 py-2.5">
            <Skeleton className={cn("h-4 rounded-md", width(row))} />
            <Skeleton className="h-3 w-10 rounded-md" />
          </div>
          {times(columns).map((column) => (
            <div key={column} className="px-2 py-2">
              <Skeleton className="h-9 w-full rounded-md" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export {
  Skeleton,
  SkeletonCard,
  SkeletonFields,
  SkeletonGrid,
  SkeletonList,
  SkeletonPageHeader,
  SkeletonRows,
  SkeletonStatRow,
  SkeletonTable,
  SkeletonTableRows,
  SkeletonTabs,
  SkeletonText,
  SkeletonToolbar,
};
