import type { ComponentProps, ReactNode } from "react";

import { cn } from "#lib/utils";

/*
 * A list table's phone layout (`< 768px`): one card per row, inside the same `Card` that holds
 * the table on wider screens. Each item reads top to bottom: who or what it is with its status,
 * then its settings or figures, then full-width actions. Pass the table's label as `aria-label`
 * so the list is announced by the same name.
 */

function PhoneCardList({ className, ...props }: ComponentProps<"ul">) {
  return <ul className={cn("divide-y divide-border", className)} {...props} />;
}

function PhoneCardItem({ className, ...props }: ComponentProps<"li">) {
  return <li className={cn("min-w-0 space-y-3 p-4", className)} {...props} />;
}

/** The item's name over an optional detail line, with its status on the right. */
function PhoneCardHeader({
  title,
  subtitle,
  status,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  status?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-3", className)}>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold break-words">{title}</p>
        {subtitle ? (
          <p className="mt-0.5 text-xs break-words text-muted-foreground">{subtitle}</p>
        ) : null}
      </div>
      {status ? <div className="flex shrink-0 flex-wrap justify-end gap-1.5">{status}</div> : null}
    </div>
  );
}

/** Two columns of labelled settings or figures; a field spans both with `col-span-2`. */
function PhoneCardFields({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("grid grid-cols-2 gap-2.5", className)} {...props} />;
}

function PhoneCardField({
  label,
  children,
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid min-w-0 content-start gap-1", className)}>
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

/** Full-width actions stacked under the item; grid cells stretch each to an easy thumb target. */
function PhoneCardActions({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("grid grid-cols-1 gap-2", className)} {...props} />;
}

export {
  PhoneCardActions,
  PhoneCardField,
  PhoneCardFields,
  PhoneCardHeader,
  PhoneCardItem,
  PhoneCardList,
};
