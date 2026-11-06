import { appShellLabels } from "@flrc/i18n";
import { Outlet, createFileRoute, Link, redirect, useMatch } from "@tanstack/react-router";
import { useIsFetching, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { FileTextIcon, LayoutGridIcon, ShieldCheckIcon } from "lucide-react";
import { getGridOptions, listClassCatalogOptions, sessionOptions } from "@flrc/api-client";
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
import { REPORT_GRADES, reportClasses } from "../class-report/scope";

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

// One public origin serves both panels (ADR-022); development runs them on two ports.
const adminUrl =
  import.meta.env.VITE_ADMIN_URL ??
  (import.meta.env.DEV ? "http://localhost:5174/admin/" : "/admin/");

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
  const reportMatch = useMatch({ from: "/_auth/class-report/$classId", shouldThrow: false });
  const gridMatch = useMatch({ from: "/_auth/classes/$classId/$subject", shouldThrow: false });
  const englishGrid = gridMatch?.params.subject === "english" ? gridMatch : undefined;
  // The English grid on screen is already in the cache under the same key, in whichever year
  // and semester it shows; read its grade from there instead of the active-year catalog.
  const { data: grid } = useQuery({
    ...getGridOptions({
      path: { class_id: Number(englishGrid?.params.classId) },
      query: { subject: "english", semester: englishGrid?.search.semester },
    }),
    enabled: false,
  });
  const reportOpen = reportMatch !== undefined;

  // Class reports are for middle-school English teachers; only they get the entry. It opens
  // the report of the class on screen when that is a middle-school English class.
  const myReportClasses = reportClasses(catalog, { mine: true });
  const reportTarget = reportMatch
    ? { classId: reportMatch.params.classId, semester: reportMatch.search.semester }
    : englishGrid && grid && REPORT_GRADES.includes(grid.meta.grade_level)
      ? { classId: englishGrid.params.classId, semester: grid.meta.semester_number }
      : myReportClasses[0]
        ? { classId: String(myReportClasses[0].id), semester: undefined }
        : null;
  // While a class report is open the shortcuts open reports of the teacher's middle-school
  // English classes, which stay useful after a semester closes.
  const myBoards = reportOpen
    ? myReportClasses.map((schoolClass) => ({ schoolClass, subject: "english" as const }))
    : catalog.flatMap((schoolClass) =>
        schoolClass.subjects
          .filter((subject) => subject.can_write)
          .map((subject) => ({ schoolClass, subject: subject.subject })),
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
        {myReportClasses.length && reportTarget ? (
          <Link
            to="/class-report/$classId"
            params={{ classId: reportTarget.classId }}
            search={{ semester: reportTarget.semester }}
            className={sidebarItemClass}
            activeProps={{ className: sidebarItemActiveClass }}
            activeOptions={{ includeSearch: false }}
            onClick={onNavigate}
          >
            <FileTextIcon />
            {t("classReport.nav")}
          </Link>
        ) : null}
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
          {myBoards.map(({ schoolClass, subject }) => {
            const label = (
              <>
                <span className="tabular w-8 shrink-0 text-xs text-muted-foreground">
                  {schoolClass.name}
                </span>
                <span className="truncate">{t(`subjects.${subject}`)}</span>
              </>
            );
            const shared = {
              search: { semester: undefined },
              className: sidebarItemClass,
              activeProps: { className: sidebarItemActiveClass },
              onClick: onNavigate,
            };
            return reportOpen ? (
              <Link
                key={`${schoolClass.id}-${subject}`}
                {...shared}
                to="/class-report/$classId"
                params={{ classId: String(schoolClass.id) }}
              >
                {label}
              </Link>
            ) : (
              <Link
                key={`${schoolClass.id}-${subject}`}
                {...shared}
                to="/classes/$classId/$subject"
                params={{ classId: String(schoolClass.id), subject }}
              >
                {label}
              </Link>
            );
          })}
        </SidebarSection>
      ) : null}
    </>
  );
}
