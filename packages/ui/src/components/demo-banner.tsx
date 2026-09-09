import { useEffect, useState, type ReactNode } from "react";

import { cn } from "#lib/utils";

/** Minutes until an ISO instant, never negative; a partial minute counts as one. */
export function minutesUntil(iso: string, now: number = Date.now()): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 60_000));
}

/** "23:00" in the viewer's locale and timezone, for a reset that happens at a fixed instant. */
export function formatClockTime(iso: string, locale: string): string {
  return new Date(iso).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

const SOON_MINUTES = 15;

/**
 * The strip a demo visitor sees on every page: the shared school resets at a
 * fixed instant and unsaved edits go with it. Calm until the final quarter
 * hour, then a warning so a mid-entry visitor saves in time.
 */
export function DemoBanner({
  nextResetAt,
  locale,
  render,
  className,
}: {
  nextResetAt: string;
  locale: string;
  render: (state: { minutesLeft: number; soon: boolean; resetTime: string }) => ReactNode;
  className?: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  const minutesLeft = minutesUntil(nextResetAt, now);
  const soon = minutesLeft <= SOON_MINUTES;

  return (
    <div
      role="status"
      aria-live={soon ? "assertive" : "polite"}
      className={cn(
        "mb-4 rounded-lg border px-3 py-2 text-xs font-medium",
        soon
          ? "border-warning/40 bg-warning-surface text-warning"
          : "border-border bg-muted text-muted-foreground",
        className,
      )}
    >
      {render({ minutesLeft, soon, resetTime: formatClockTime(nextResetAt, locale) })}
    </div>
  );
}
