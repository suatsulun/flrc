import { appShellLabels } from "@flrc/i18n";
import { Outlet, createFileRoute, Link, redirect } from "@tanstack/react-router";
import { useIsFetching, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { LayoutGridIcon, ShieldCheckIcon } from "lucide-react";
import { listClassCatalogOptions, sessionOptions } from "@flrc/api-client";
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

export const Route = createFileRoute("/_auth")({
  beforeLoad: async ({ context }) => {
    try {
      const user = await context.queryClient.ensureQueryData(sessionOptions());
      return { user };
    } catch {
      throw redirect({ to: "/login" });
    }
  },
  component: AuthLayout,
});

const adminUrl = import.meta.env.VITE_ADMIN_URL ?? "http://localhost:5174/admin/";

function AuthLayout() {
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
    window.location.replace("/login");
  };

  return (
    <AppShell
      schoolName={SCHOOL_SHORT_NAME}
      schoolLogoUrl={LOGO_URL}
      workspaceLabel={t("shell.teacherWorkspace")}
      user={user}
      onLogout={logout}
      labels={appShellLabels(t)}
      renderHome={(props) => <Link to="/" {...props} />}
      renderNav={({ onNavigate }) => (
        <TeacherNavigation isAdmin={user.is_admin} onNavigate={onNavigate} />
      )}
      topbarActions={
        <LanguageSwitch
          language={i18n.language}
          onChange={(language) => void i18n.changeLanguage(language)}
          ariaLabel={t("shell.language")}
        />
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

function TeacherNavigation({ isAdmin, onNavigate }: { isAdmin: boolean; onNavigate: () => void }) {
  const { t } = useTranslation();
  // Shares the dashboard's cache entry, so this costs no extra request.
  const { data: catalog = [] } = useQuery(listClassCatalogOptions());

  const myBoards = catalog.flatMap((schoolClass) =>
    schoolClass.subjects
      .filter((subject) => subject.can_write)
      .map((subject) => ({ schoolClass, subject })),
  );

  return (
    <>
      <SidebarSection>
        <Link
          to="/"
          className={sidebarItemClass}
          activeProps={{ className: sidebarItemActiveClass }}
          activeOptions={{ exact: true }}
          onClick={onNavigate}
        >
          <LayoutGridIcon />
          {t("dashboard.allClasses")}
        </Link>
        {isAdmin ? (
          <a href={adminUrl} className={sidebarItemClass}>
            <ShieldCheckIcon />
            {t("goToAdmin")}
          </a>
        ) : null}
      </SidebarSection>

      {/* The boards this teacher is actually responsible for — the whole point
          of the sidebar, and one click from anywhere. */}
      {myBoards.length ? (
        <SidebarSection label={t("dashboard.myAssignments")}>
          {myBoards.map(({ schoolClass, subject }) => (
            <Link
              key={`${schoolClass.id}-${subject.subject}`}
              to="/classes/$classId/$subject"
              params={{ classId: String(schoolClass.id), subject: subject.subject }}
              search={{ semester: undefined }}
              className={sidebarItemClass}
              activeProps={{ className: sidebarItemActiveClass }}
              onClick={onNavigate}
            >
              <span className="tabular w-8 shrink-0 text-xs text-muted-foreground">
                {schoolClass.name}
              </span>
              <span className="truncate">{t(`subjects.${subject.subject}`)}</span>
            </Link>
          ))}
        </SidebarSection>
      ) : null}
    </>
  );
}
