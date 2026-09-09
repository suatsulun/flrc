import {
  MenuIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PanelTopCloseIcon,
  PanelTopOpenIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import { Button } from "#components/button";
import { SchoolLogo } from "#components/school-logo";
import { ThemeToggle } from "#components/theme-toggle";
import { cn } from "#lib/utils";
import type { ThemePreference } from "#lib/theme";

export type AppShellLabels = {
  menu: string;
  closeMenu: string;
  mainNavigation: string;
  skipToContent: string;
  logout: string;
  collapseSidebar: string;
  expandSidebar: string;
  collapseHeader: string;
  expandHeader: string;
  theme: Record<ThemePreference, string>;
};

const SIDEBAR_KEY = "flrc-shell-sidebar-collapsed";
const HEADER_KEY = "flrc-shell-header-collapsed";

function readCollapsed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "true";
  } catch {
    return false;
  }
}

function storeCollapsed(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Storage can be unavailable in a hardened/private browser. The control
    // still works for the current page without persistence.
  }
}

/**
 * The chrome both apps share: a slim top bar with the school logo at the far
 * left, a grouped sidebar, and the theme control pinned to the bottom-left.
 *
 * Navigation *content* is passed in rather than described in data, because each
 * app owns its own router and this package has no router dependency. `renderNav`
 * receives `onNavigate` so tapping a link on a phone also closes the drawer.
 */
export function AppShell({
  schoolName,
  schoolLogoUrl,
  workspaceLabel,
  user,
  labels,
  onLogout,
  renderHome,
  renderNav,
  topbarActions,
  contentClassName,
  children,
}: {
  schoolName: string;
  /** Where the logo file lives; base-prefixed by the app. */
  schoolLogoUrl?: string;
  workspaceLabel: string;
  user: { full_name: string; email: string };
  labels: AppShellLabels;
  onLogout: () => void | Promise<void>;
  renderHome: (props: { className: string; children: ReactNode }) => ReactNode;
  renderNav: (props: { onNavigate: () => void }) => ReactNode;
  /** Right-hand side of the top bar — language switch, cross-app links. */
  topbarActions?: ReactNode;
  contentClassName?: string;
  children: ReactNode;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => readCollapsed(SIDEBAR_KEY));
  const [headerCollapsed, setHeaderCollapsed] = useState(() => readCollapsed(HEADER_KEY));
  const shellStyle = {
    "--app-shell-header-height": headerCollapsed ? "2.25rem" : "3.5rem",
  } as CSSProperties;

  const toggleSidebar = () => {
    setSidebarCollapsed((collapsed) => {
      storeCollapsed(SIDEBAR_KEY, !collapsed);
      return !collapsed;
    });
  };
  const toggleHeader = () => {
    setHeaderCollapsed((collapsed) => {
      storeCollapsed(HEADER_KEY, !collapsed);
      return !collapsed;
    });
  };
  const logout = async () => {
    if (logoutPending) return;
    setLogoutPending(true);
    try {
      await onLogout();
    } finally {
      setLogoutPending(false);
    }
  };

  useEffect(() => {
    if (!drawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  const home = renderHome({
    className:
      "flex min-w-0 items-center gap-2.5 rounded-lg px-1 py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
    children: (
      <>
        <SchoolLogo src={schoolLogoUrl} schoolName={schoolName} />
        <span className="min-w-0">
          <span className="block truncate text-[0.8125rem] leading-4 font-semibold tracking-tight">
            {schoolName}
          </span>
          <span className="hidden truncate text-[0.6875rem] leading-4 text-muted-foreground sm:block">
            {workspaceLabel}
          </span>
        </span>
      </>
    ),
  });

  return (
    <div className="min-h-svh bg-background" style={shellStyle}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-100 focus:rounded-lg focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-overlay"
      >
        {labels.skipToContent}
      </a>

      <header
        className={cn(
          "sticky top-0 z-40 border-b border-border bg-card/85 backdrop-blur-md transition-[height]",
          headerCollapsed ? "h-9" : "h-14",
        )}
      >
        <div className="flex h-full items-center gap-2 px-2 sm:px-3">
          <Button
            className="hidden md:inline-flex"
            variant="ghost"
            size="icon-sm"
            aria-label={sidebarCollapsed ? labels.expandSidebar : labels.collapseSidebar}
            aria-pressed={sidebarCollapsed}
            onClick={toggleSidebar}
          >
            {sidebarCollapsed ? <PanelLeftOpenIcon /> : <PanelLeftCloseIcon />}
          </Button>

          {headerCollapsed ? (
            <div className="hidden min-w-0 items-center md:flex">
              <SchoolLogo src={schoolLogoUrl} schoolName={schoolName} />
            </div>
          ) : (
            home
          )}

          <div className="ml-auto flex items-center gap-2">
            <div
              className={cn("hidden items-center gap-2 md:flex", headerCollapsed && "md:hidden")}
            >
              {topbarActions}
            </div>

            <div
              className={cn(
                "hidden items-center gap-2.5 border-l border-border pl-3 md:flex",
                headerCollapsed && "md:hidden",
              )}
            >
              <div className="hidden text-right lg:block">
                <p className="max-w-40 truncate text-[0.8125rem] leading-4 font-medium">
                  {user.full_name}
                </p>
                <p className="max-w-40 truncate text-[0.6875rem] leading-4 text-muted-foreground">
                  {user.email}
                </p>
              </div>
              <Avatar name={user.full_name} />
              <Button
                size="sm"
                variant="outline"
                pending={logoutPending}
                pendingLabel={labels.logout}
                onClick={() => void logout()}
              >
                {labels.logout}
              </Button>
            </div>

            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={headerCollapsed ? labels.expandHeader : labels.collapseHeader}
              aria-pressed={headerCollapsed}
              onClick={toggleHeader}
            >
              {headerCollapsed ? <PanelTopOpenIcon /> : <PanelTopCloseIcon />}
            </Button>

            <Button
              className="md:hidden"
              variant="outline"
              size="icon-sm"
              aria-expanded={drawerOpen}
              aria-controls="app-shell-drawer"
              aria-label={drawerOpen ? labels.closeMenu : labels.menu}
              onClick={() => setDrawerOpen((open) => !open)}
            >
              {drawerOpen ? <XIcon /> : <MenuIcon />}
            </Button>
          </div>
        </div>
      </header>

      <div
        className={cn(
          "md:grid",
          sidebarCollapsed
            ? "md:grid-cols-[0_minmax(0,1fr)]"
            : "md:grid-cols-[15rem_minmax(0,1fr)]",
        )}
      >
        <aside
          className={cn(
            "sticky hidden flex-col border-r border-border bg-sidebar md:flex",
            sidebarCollapsed && "invisible overflow-hidden border-r-0",
          )}
          style={{
            top: "var(--app-shell-header-height)",
            height: "calc(100svh - var(--app-shell-header-height))",
          }}
        >
          <nav
            aria-label={labels.mainNavigation}
            className="min-h-0 flex-1 overflow-y-auto px-2.5 py-4"
          >
            {renderNav({ onNavigate: () => undefined })}
          </nav>
          <div className="border-t border-border p-2.5">
            <ThemeToggle labels={labels.theme} />
          </div>
        </aside>

        <main id="main" className={cn("min-w-0", contentClassName ?? defaultContentClass)}>
          {children}
        </main>
      </div>

      {drawerOpen ? (
        <div
          id="app-shell-drawer"
          className="fixed inset-0 z-50 md:hidden"
          style={{ top: "var(--app-shell-header-height)" }}
        >
          <button
            type="button"
            className="absolute inset-0 bg-foreground/25 backdrop-blur-sm"
            aria-label={labels.closeMenu}
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="absolute inset-y-0 right-0 flex w-[min(88vw,20rem)] flex-col border-l border-border bg-card shadow-overlay">
            <div className="flex items-center gap-2.5 border-b border-border p-4">
              <Avatar name={user.full_name} />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{user.full_name}</p>
                <p className="truncate text-xs text-muted-foreground">{user.email}</p>
              </div>
            </div>
            <nav
              aria-label={labels.mainNavigation}
              className="min-h-0 flex-1 overflow-y-auto px-2.5 py-4"
            >
              {renderNav({ onNavigate: () => setDrawerOpen(false) })}
            </nav>
            <div className="space-y-3 border-t border-border p-4">
              <div className="flex items-center justify-between gap-2 md:hidden">
                {topbarActions}
              </div>
              <div className="flex items-center justify-between gap-2">
                <ThemeToggle labels={labels.theme} />
                <Button
                  size="sm"
                  variant="outline"
                  pending={logoutPending}
                  pendingLabel={labels.logout}
                  onClick={() => void logout()}
                >
                  {labels.logout}
                </Button>
              </div>
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

const defaultContentClass = "w-full min-w-0 space-y-4 px-2 py-3 sm:px-3 lg:px-4";

function Avatar({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toLocaleUpperCase();
  return (
    <span
      aria-hidden
      className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-[0.6875rem] font-semibold text-accent-foreground"
    >
      {initials}
    </span>
  );
}

/** Labelled group of sidebar links. */
export function SidebarSection({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <section className="mb-4 last:mb-0">
      {label ? (
        <h2 className="mb-1 px-2.5 text-[0.625rem] font-semibold tracking-[0.12em] text-muted-foreground uppercase">
          {label}
        </h2>
      ) : null}
      <div className="space-y-0.5">{children}</div>
    </section>
  );
}

/**
 * Classes for sidebar links. Exported as strings so each app can hand them to
 * its router's `activeProps`, which is what actually knows the current route.
 */
export const sidebarItemClass =
  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.8125rem] font-medium text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 [&_svg]:size-4 [&_svg]:shrink-0";

export const sidebarItemActiveClass =
  "bg-accent text-accent-foreground hover:bg-accent hover:text-accent-foreground";
