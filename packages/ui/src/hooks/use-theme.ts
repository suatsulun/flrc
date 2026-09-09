import { useCallback, useEffect, useState } from "react";

import {
  applyTheme,
  onThemeChange,
  readThemePreference,
  resolveTheme,
  setThemePreference,
  type ResolvedTheme,
  type ThemePreference,
} from "#lib/theme";

/**
 * Reads and writes the theme preference. Stays in sync with the OS while the
 * preference is `system`, and with every other `useTheme` caller on the page.
 */
export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(readThemePreference);
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    resolveTheme(readThemePreference()),
  );

  useEffect(() => {
    const sync = () => {
      const next = readThemePreference();
      setPreference(next);
      setResolved(applyTheme(next));
    };
    sync();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", sync);
    const unsubscribe = onThemeChange(sync);
    return () => {
      media.removeEventListener("change", sync);
      unsubscribe();
    };
  }, []);

  const setTheme = useCallback((next: ThemePreference) => setThemePreference(next), []);

  return { preference, resolved, setTheme };
}
