import { appShellLabels } from "@flrc/i18n";
import { Outlet, createFileRoute, Link, redirect } from "@tanstack/react-router";
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  ArchiveIcon,
  CalendarDaysIcon,
  ClipboardListIcon,
  FileTextIcon,
  GaugeIcon,
  HistoryIcon,
  KeyRoundIcon,
  LayoutDashboardIcon,
  SchoolIcon,
  UploadIcon,
} from "lucide-react";
import { sessionOptions } from "@flrc/api-client";
import {
  AppShell,
  SidebarSection,
  sidebarItemActiveClass,
  sidebarItemClass,
} from "@flrc/ui/components/app-shell";
import { DemoBanner } from "@flrc/ui/components/demo-banner";
import { PageActivity } from "@flrc/ui/components/page-activity";

import { LanguageSwitch } from "@flrc/ui/components/language-switch";
import { LOGO_URL, SCHOOL_SHORT_NAME } from "@flrc/branding";

const teacherUrl = import.meta.env.VITE_TEACHER_URL ?? "http://localhost:5173";

export const Route = createFileRoute("/_auth")({
  beforeLoad: async ({ context }) => {
    const user = await context.queryClient.ensureQueryData(sessionOptions()).catch(() => {
      throw redirect({ href: `${teacherUrl}/login` });
    });
    if (!user.is_admin && !user.is_coordinator) throw redirect({ href: teacherUrl });
    return { user };
  },
  component: AdminLayout,
});

function AdminLayout() {
  const { user } = Route.useRouteContext();
  const { t, i18n } = useTranslation();
  const demo = user.demo;
  const queryClient = useQueryClient();
  const initialLoads = useIsFetching({
    predicate: (query) => query.state.data === undefined,
  });

  const logout = async () => {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (!response.ok) {
      toast.error(t("feedback.actionFailed"));
      return;
    }
    queryClient.clear();
    window.location.replace(`${teacherUrl}/login`);
  };

  return (
    <AppShell
      schoolName={SCHOOL_SHORT_NAME}
      schoolLogoUrl={LOGO_URL}
      workspaceLabel={t("shell.adminWorkspace")}
      user={user}
      onLogout={logout}
      labels={appShellLabels(t)}
      renderHome={(props) => <Link to="/" {...props} />}
      renderNav={({ onNavigate }) => (
        <AdminNavigation isAdmin={user.is_admin} onNavigate={onNavigate} />
      )}
      topbarActions={
        <>
          <LanguageSwitch
            language={i18n.language}
            onChange={(language) => void i18n.changeLanguage(language)}
            ariaLabel={t("shell.language")}
          />
          <a
            href={teacherUrl}
            className="hidden rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground lg:block"
          >
            {t("goToTeacher")}
          </a>
        </>
      }
    >
      {demo ? (
        <DemoBanner
          nextResetAt={demo.next_reset_at}
          locale={i18n.language}
          render={({ minutesLeft, soon, resetTime }) =>
            soon
              ? t("demo.bannerSoon", { minutes: minutesLeft })
              : t("demo.banner", { time: resetTime })
          }
        />
      ) : null}
      <PageActivity active={initialLoads > 0} label={t("loading")} />
      <Outlet />
    </AppShell>
  );
}

function AdminNavigation({ isAdmin, onNavigate }: { isAdmin: boolean; onNavigate: () => void }) {
  const { t } = useTranslation();

  const groups = [
    {
      label: t("shell.navOverview"),
      items: [
        isAdmin
          ? { to: "/classes", label: t("classWorkspace.title"), Icon: SchoolIcon }
          : { to: "/", label: t("shell.overview"), Icon: LayoutDashboardIcon, exact: true },
      ],
    },
    ...(isAdmin
      ? [
          {
            label: t("shell.navPeople"),
            items: [{ to: "/users", label: t("users.title"), Icon: KeyRoundIcon }],
          },
          {
            label: t("shell.navSetup"),
            items: [
              { to: "/assignments", label: t("assignments.title"), Icon: ClipboardListIcon },
              { to: "/lifecycle", label: t("lifecycle.title"), Icon: CalendarDaysIcon },
              { to: "/import", label: t("import.title"), Icon: UploadIcon },
            ],
          },
        ]
      : []),
    {
      label: t("shell.navOperations"),
      items: [
        ...(isAdmin ? [{ to: "/audit", label: t("audit.title"), Icon: HistoryIcon }] : []),
        { to: "/coordinator", label: t("coordinator.title"), Icon: GaugeIcon },
        { to: "/reports", label: t("reports.title"), Icon: FileTextIcon },
        { to: "/archive", label: t("archive.title"), Icon: ArchiveIcon },
      ],
    },
  ];

  return (
    <>
      {groups.map((group) => (
        <SidebarSection key={group.label} label={group.label}>
          {group.items.map(({ to, label, Icon, ...rest }) => (
            <Link
              key={to}
              to={to}
              className={sidebarItemClass}
              activeProps={{ className: sidebarItemActiveClass }}
              activeOptions={"exact" in rest ? { exact: rest.exact } : undefined}
              onClick={onNavigate}
            >
              <Icon />
              {label}
            </Link>
          ))}
        </SidebarSection>
      ))}
    </>
  );
}
