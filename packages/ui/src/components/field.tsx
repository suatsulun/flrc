import { useId, type ReactNode } from "react";

import { Label } from "#components/label";
import { cn } from "#lib/utils";

/**
 * Label + control + hint/error, wired together.
 *
 * `children` receives the generated id so the label always points at the real
 * control, whatever it is (input, select, file picker).
 */
export function Field({
  label,
  hint,
  error,
  className,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  const messageId = `${id}-message`;

  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={id} className="text-[0.8125rem] font-medium text-foreground">
        {label}
      </Label>
      {children(id)}
      {error ? (
        <p id={messageId} className="text-xs text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={messageId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
