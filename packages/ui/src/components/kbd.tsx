import type { ReactNode } from "react";

import { cn } from "#lib/utils";

/** Renders a key name inline, for the keyboard hints around the grade grid. */
export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-muted px-1.5",
        "font-sans text-[0.6875rem] font-medium text-muted-foreground",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

/** `true` on macOS, so hints can say ⌘ instead of Ctrl. */
export const isMacPlatform = () =>
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
