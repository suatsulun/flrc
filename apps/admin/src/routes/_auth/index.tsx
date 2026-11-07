import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { getDashboardOptions } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { Stat, StatRow } from "@flrc/ui/components/stat";
import { AdminPage } from "../../admin/AdminPage";
import { CompletionCard } from "../../dashboard/CompletionCard";
import { JobsCard } from "../../dashboard/JobsCard";
import { ReadinessCard } from "../../dashboard/ReadinessCard";
import { RecentChangesCard } from "../../dashboard/RecentChangesCard";
import { SetupProblemsCard } from "../../dashboard/SetupProblemsCard";
import { TermCard } from "../../dashboard/TermCard";

export const Route = createFileRoute("/_auth/")({ component: Dashboard });

/** The landing page of admins and coordinators (ADR-079). */
function Dashboard() {
  const { user } = Route.useRouteContext();
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery(getDashboardOptions());

  if (isPending) return <PageSkeleton />;
  if (isError) return <EmptyState title={t("errors.load")} />;

  const { term, overview, completion, problems, readiness } = data;
  const stats = [
    ["students", overview.students, "default"],
    ["classes", overview.classes, "default"],
    ["teachers", overview.active_teachers, "default"],
    ["grants", overview.active_grants, "default"],
    ["saves", overview.recent_saves, "default"],
    [
      "missingAssignments",
      overview.missing_assignments,
      overview.missing_assignments > 0 ? "warning" : "success",
    ],
  ] as const;

  return (
    <AdminPage
      title={t("greeting", { name: user.full_name })}
      description={t("adminDashboard.subtitle")}
      meta={
        term.year_label ? (
          <Badge tone="info">
            {term.year_label}
            {term.semester_number
              ? ` · ${t("lifecycle.semester", { number: term.semester_number })}`
              : ""}
          </Badge>
        ) : null
      }
    >
      <StatRow className="grid-cols-2">
        {stats.map(([key, value, tone]) => (
          <Stat key={key} value={value} label={t(`coordinator.${key}`)} tone={tone} />
        ))}
      </StatRow>

      {/* minmax(0, 1fr) tracks: a wide table scrolls inside its card instead of widening the page. */}
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <TermCard term={term} step={data.next_step} isAdmin={user.is_admin} />
        {problems && term.year_id ? (
          <SetupProblemsCard problems={problems} yearId={term.year_id} isAdmin={user.is_admin} />
        ) : null}
        {completion && term.year_id ? (
          <CompletionCard completion={completion} yearId={term.year_id} isAdmin={user.is_admin} />
        ) : null}
        {completion && readiness.length ? (
          <ReadinessCard readiness={readiness} semesterNumber={completion.semester_number} />
        ) : null}
        {user.is_admin ? <RecentChangesCard /> : null}
        <JobsCard />
      </div>
    </AdminPage>
  );
}
