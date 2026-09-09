import type { ComponentProps, ReactNode } from "react";

import { cn } from "#lib/utils";

/** A keyboard-scrollable viewport that keeps wide tables inside their card. */
function TableScroll({ className, tabIndex = 0, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="table-scroll"
      tabIndex={tabIndex}
      className={cn(
        "flrc-table-scroll max-h-[min(70svh,48rem)] w-full min-w-0 overflow-auto overscroll-contain rounded-[inherit]",
        "outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50",
        className,
      )}
      {...props}
    />
  );
}

function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <table
      className={cn(
        "w-max min-w-full table-auto border-separate border-spacing-0 text-sm",
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("bg-muted/85", className)} {...props} />;
}

function TableBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody className={className} {...props} />;
}

function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      className={cn(
        "group transition-colors even:bg-muted/20 hover:bg-accent/45 focus-within:bg-accent/55",
        className,
      )}
      {...props}
    />
  );
}

function TableHeader({ className, align, ...props }: ComponentProps<"th">) {
  return (
    <th
      scope="col"
      className={cn(
        "sticky top-0 z-20 border-b border-border bg-muted/95 px-3 py-2.5 text-left align-middle whitespace-nowrap backdrop-blur",
        "text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, align, ...props }: ComponentProps<"td">) {
  return (
    <td
      className={cn(
        "border-b border-border/70 px-3 py-2.5 align-middle whitespace-nowrap",
        align === "right" && "tabular-nums text-right",
        align === "center" && "tabular-nums text-center",
        className,
      )}
      {...props}
    />
  );
}

/** Intentionally truncates long text while preserving the full value on hover. */
function TableText({ className, title, children, ...props }: ComponentProps<"span">) {
  const tooltip = title ?? (typeof children === "string" ? children : undefined);
  return (
    <span className={cn("block max-w-64 truncate", className)} title={tooltip} {...props}>
      {children}
    </span>
  );
}

function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("sr-only", className)} {...props} />;
}

/**
 * Full-width "nothing here" row that keeps the table's shape.
 *
 * A wide table is usually scrolled horizontally, and a message centred across
 * the full table width would sit outside the visible viewport. The message
 * therefore sticks to the left edge of the scroll viewport instead.
 */
function TableEmpty({
  colSpan,
  children,
  className,
}: {
  colSpan: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <tr>
      <td colSpan={colSpan} className="p-0">
        <div
          className={cn(
            "sticky left-0 inline-block px-4 py-12 text-sm text-muted-foreground",
            className,
          )}
        >
          {children}
        </div>
      </td>
    </tr>
  );
}

export {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
  TableScroll,
  TableText,
};
