import { useEffect } from "react";

/** Warm nearby class tabs after navigation settles; stop when the scope changes. */
export function usePrefetchSiblings(
  items: readonly { id: number }[],
  prefetch: (id: number) => Promise<void>,
) {
  useEffect(() => {
    if (items.length < 2) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      for (const item of items) {
        if (cancelled) return;
        await prefetch(item.id);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [items, prefetch]);
}
