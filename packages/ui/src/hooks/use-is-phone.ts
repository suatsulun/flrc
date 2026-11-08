import { useCallback, useSyncExternalStore } from "react";

/** Below Tailwind's `md` breakpoint, where `AppShell` swaps its sidebar for the drawer. */
export const PHONE_MEDIA_QUERY = "(max-width: 767px)";

const lists = new Map<string, MediaQueryList>();

function mediaList(query: string): MediaQueryList {
  let list = lists.get(query);
  if (!list) {
    list = window.matchMedia(query);
    lists.set(query, list);
  }
  return list;
}

/** Whether `query` matches now, re-rendering when it starts or stops matching. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = mediaList(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => mediaList(query).matches);
}

/**
 * Whether the viewport is phone-sized (`< 768px`). Use it only where both layouts cannot be
 * mounted together, e.g. form controls that would otherwise exist twice; plain layout swaps
 * belong in CSS (`md:hidden` / `hidden md:block`) so they match the viewport before hydration.
 */
export function useIsPhone(): boolean {
  return useMediaQuery(PHONE_MEDIA_QUERY);
}
