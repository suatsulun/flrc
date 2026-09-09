/**
 * Theme preference: `system` follows the OS, `light`/`dark` pin a side.
 *
 * The resolved theme is stamped on <html> as a `light` or `dark` class so the
 * `dark:` variant in `styles/theme.css` can key off it.
 *
 * Each app also ships `public/theme-boot.js`, loaded blocking from <head>, which
 * stamps the same class before the first paint so an overridden preference never
 * flashes the wrong palette. It is a static file rather than inline script
 * because the apps run under `script-src 'self'`. Keep `applyTheme` below and
 * that file in agreement.
 */

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "flrc-theme";
const THEME_EVENT = "flrc:themechange";

const isPreference = (value: unknown): value is ThemePreference =>
  value === "light" || value === "dark" || value === "system";

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isPreference(stored) ? stored : "system";
  } catch {
    // Private-mode Safari throws on localStorage access; the OS setting still works.
    return "system";
  }
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== "system") return preference;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(preference: ThemePreference): ResolvedTheme {
  const resolved = resolveTheme(preference);
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.classList.toggle("light", resolved === "light");
  root.style.colorScheme = resolved;
  return resolved;
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    if (preference === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Preference simply will not survive a reload; applying it now still works.
  }
  applyTheme(preference);
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: preference }));
}

/** Subscribe to preference changes from any `ThemeToggle` on the page. */
export function onThemeChange(listener: () => void): () => void {
  window.addEventListener(THEME_EVENT, listener);
  return () => window.removeEventListener(THEME_EVENT, listener);
}
