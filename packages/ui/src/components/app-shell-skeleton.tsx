import type { CSSProperties, ReactNode } from "react";

import { LoadingStatus } from "#components/page-activity";
import { SchoolLogo } from "#components/school-logo";
import { Skeleton } from "#components/skeleton";
import { cn } from "#lib/utils";

// The layout choices `AppShell` stores; read here so the first paint matches the shell.
const SIDEBAR_KEY = "flrc-shell-sidebar-collapsed";
const HEADER_KEY = "flrc-shell-header-collapsed";

function readCollapsed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "true";
  } catch {
    return false;
  }
}

/**
 * `AppShell` before the session is known: the real school mark, the sidebar's sections and
 * the top bar's controls as placeholders, and the target page's skeleton as content. The
 * first app load shows this instead of an empty screen with a spinner.
 */
export function AppShellSkeleton({
  schoolName,
  schoolLogoUrl,
  workspaceLabel,
  navGroups,
  label,
  children,
}: {
  schoolName: string;
  schoolLogoUrl?: string;
  workspaceLabel: string;
  /** Links per sidebar section, mirroring the app's navigation. */
  navGroups: readonly number[];
  /** The polite "Loading…" announcement. */
  label: string;
  children: ReactNode;
}) {
  const sidebarCollapsed = readCollapsed(SIDEBAR_KEY);
  const headerCollapsed = readCollapsed(HEADER_KEY);
  const shellStyle = {
    "--app-shell-header-height": headerCollapsed ? "2.25rem" : "3.5rem",
  } as CSSProperties;

  return (
    <div className="min-h-svh bg-background" style={shellStyle}>
      <LoadingStatus label={label} />
      <header
        aria-hidden
        className={cn(
          "sticky top-0 z-40 border-b border-border bg-card/85 backdrop-blur-md",
          headerCollapsed ? "h-9" : "h-14",
        )}
      >
        <div className="flex h-full items-center gap-2 px-2 sm:px-3">
          <Skeleton className="hidden size-7 md:block" />
          {headerCollapsed ? (
            <div className="hidden min-w-0 items-center md:flex">
              <SchoolLogo src={schoolLogoUrl} schoolName={schoolName} className="h-7" />
            </div>
          ) : (
            <div className="flex min-w-0 items-center gap-2.5 px-1 py-1">
              <SchoolLogo src={schoolLogoUrl} schoolName={schoolName} />
              <span className="min-w-0">
                <span className="block truncate text-[0.8125rem] leading-4 font-semibold tracking-tight">
                  {schoolName}
                </span>
                <span className="hidden truncate text-[0.6875rem] leading-4 text-muted-foreground sm:block">
                  {workspaceLabel}
                </span>
              </span>
            </div>
          )}
          <div className="ml-auto flex items-center gap-2">
            {headerCollapsed ? null : (
              <>
                <Skeleton className="hidden h-7 w-20 md:block" />
                <div className="hidden items-center gap-2.5 border-l border-border pl-3 md:flex">
                  <div className="hidden space-y-1 lg:block">
                    <Skeleton className="ml-auto h-3 w-28 rounded-md" />
                    <Skeleton className="h-2.5 w-36 rounded-md" />
                  </div>
                  <Skeleton className="size-8 rounded-full" />
                  <Skeleton className="h-8 w-20" />
                </div>
              </>
            )}
            <Skeleton className="size-7" />
            <Skeleton className="size-7 md:hidden" />
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
          aria-hidden
          className={cn(
            "sticky hidden flex-col border-r border-border bg-sidebar md:flex",
            sidebarCollapsed && "invisible overflow-hidden border-r-0",
          )}
          style={{
            top: "var(--app-shell-header-height)",
            height: "calc(100svh - var(--app-shell-header-height))",
          }}
        >
          <div className="min-h-0 flex-1 space-y-5 overflow-hidden px-2.5 py-4">
            {navGroups.map((links, group) => (
              <div key={group} className="space-y-1.5">
                {group > 0 ? <Skeleton className="mx-2.5 mb-2.5 h-2.5 w-20 rounded-md" /> : null}
                {Array.from({ length: links }, (_, link) => (
                  <div key={link} className="flex items-center gap-2.5 px-2.5 py-1.5">
                    <Skeleton className="size-4 shrink-0 rounded" />
                    <Skeleton className={cn("h-3.5 rounded-md", link % 2 ? "w-24" : "w-32")} />
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="border-t border-border p-2.5">
            <Skeleton className="h-8 w-full" />
          </div>
        </aside>

        <main className="w-full min-w-0 space-y-4 px-2 py-3 sm:px-3 lg:px-4">{children}</main>
      </div>
    </div>
  );
}
