import { ChevronDownIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "#lib/utils";

/**
 * A styled *native* <select>.
 *
 * The admin screens are dense with filters, and the platform control is both the
 * fastest to open and the best on a phone. `components/select.tsx` holds the
 * Base UI listbox for the cases that need custom option rendering.
 */
function NativeSelect({ className, children, ...props }: ComponentProps<"select">) {
  return (
    // Not `w-full`: as a flex child that would claim a whole row and push
    // sibling controls onto the next line. The wrapper hugs the select, so a
    // width passed in `className` decides the size, and a grid cell (e.g. inside
    // `Field`) still stretches it to the full column.
    <span className="relative inline-flex max-w-full min-w-0 items-center">
      <select
        data-slot="native-select"
        className={cn(
          "h-9 w-full min-w-0 max-w-full appearance-none rounded-lg border border-input bg-card py-0 pr-8 pl-3",
          "text-sm shadow-card transition-colors outline-none",
          "hover:border-border-strong focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-ring/25",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDownIcon className="pointer-events-none absolute right-2.5 size-3.5 text-muted-foreground" />
    </span>
  );
}

export { NativeSelect };
