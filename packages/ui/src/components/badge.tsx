import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "#lib/utils";

const badgeVariants = cva(
  "inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3 [&_svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "bg-muted text-muted-foreground",
        info: "bg-accent text-accent-foreground",
        success: "bg-success-surface text-success",
        warning: "bg-warning-surface text-warning",
        danger: "bg-destructive-surface text-destructive",
        outline: "border border-border text-muted-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

function Badge({
  className,
  tone,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ tone }), className)} {...props} />;
}

/** A small coloured disc — used where a badge's text would be redundant. */
function StatusDot({
  tone = "neutral",
  className,
}: {
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
  className?: string;
}) {
  const colors = {
    neutral: "bg-muted-foreground/50",
    info: "bg-primary",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-destructive",
  };
  return (
    <span aria-hidden className={cn("size-2 shrink-0 rounded-full", colors[tone], className)} />
  );
}

export { Badge, badgeVariants, StatusDot };
