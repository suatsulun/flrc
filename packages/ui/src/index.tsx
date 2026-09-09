/**
 * Convenience barrel for the design system.
 *
 * Deep imports (`@flrc/ui/components/button`) stay the norm inside the apps so
 * Vite can tree-shake per route; this entry point exists for the shell-level
 * pieces that are almost always used together.
 */
export {
  AppShell,
  SidebarSection,
  sidebarItemActiveClass,
  sidebarItemClass,
} from "#components/app-shell";
export type { AppShellLabels } from "#components/app-shell";
export { SchoolLogo } from "#components/school-logo";
export { ThemeToggle } from "#components/theme-toggle";
export { useTheme } from "#hooks/use-theme";
export {
  THEME_STORAGE_KEY,
  applyTheme,
  readThemePreference,
  resolveTheme,
  setThemePreference,
} from "#lib/theme";
export type { ResolvedTheme, ThemePreference } from "#lib/theme";
