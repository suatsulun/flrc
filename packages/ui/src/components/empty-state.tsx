import type { ReactNode } from "react";

import { cn } from "#lib/utils";

/** Says why a screen is empty and, where possible, what to do about it. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid place-items-center rounded-xl border border-dashed border-border bg-card/60 px-6 py-14 text-center",
        className,
      )}
    >
      <div className="max-w-sm">
        {icon ? (
          <div className="mx-auto mb-4 grid size-10 place-items-center rounded-lg bg-muted text-muted-foreground [&_svg]:size-5">
            {icon}
          </div>
        ) : null}
        <p className="font-heading font-semibold tracking-tight">{title}</p>
        {description ? (
          <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{description}</p>
        ) : null}
        {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
      </div>
    </div>
  );
}
