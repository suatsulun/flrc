import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { getDashboardOptions } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Skeleton, SkeletonStatRow } from "@flrc/ui/components/skeleton";
import { Stat, StatRow } from "@flrc/ui/components/stat";
import { AdminPage } from "../../admin/AdminPage";
import { DashboardSummaryCardsSkeleton } from "../../admin/page-skeletons";
import { CompletionCard } from "../../dashboard/CompletionCard";
import { JobsCard } from "../../dashboard/JobsCard";
import { ReadinessCard } from "../../dashboard/ReadinessCard";
import { RecentChangesCard } from "../../dashboard/RecentChangesCard";
import { SetupProblemsCard } from "../../dashboard/SetupProblemsCard";
import { TermCard } from "../../dashboard/TermCard";

export const Route = createFileRoute("/_auth/")({ component: Dashboard });

/**
 * The landing page of admins and coordinators (ADR-079). Each card loads on its own: the
 * summary cards wait for the dashboard request, Recent changes and Jobs for theirs.
 */
function Dashboard() {
  const { user } = Route.useRouteContext();
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery(getDashboardOptions());
  const term = data?.term;

  return (
    <AdminPage
      title={t("greeting", { name: user.full_name })}
      description={t("adminDashboard.subtitle")}
      meta={
        isPending ? (
          <Skeleton className="h-5 w-32 rounded-full" />
        ) : term?.year_label ? (
          <Badge tone="info">
            {term.year_label}
            {term.semester_number
              ? ` · ${t("lifecycle.semester", { number: term.semester_number })}`
              : ""}
          </Badge>
        ) : null
      }
    >
      {isPending ? (
        <SkeletonStatRow className="grid-cols-2" />
      ) : isError ? (
        <EmptyState title={t("errors.load")} />
      ) : (
        <StatRow className="grid-cols-2">
          {(
            [
              ["students", data.overview.students, "default"],
              ["classes", data.overview.classes, "default"],
              ["teachers", data.overview.active_teachers, "default"],
              ["grants", data.overview.active_grants, "default"],
              ["saves", data.overview.recent_saves, "default"],
              [
                "missingAssignments",
                data.overview.missing_assignments,
                data.overview.missing_assignments > 0 ? "warning" : "success",
              ],
            ] as const
          ).map(([key, value, tone]) => (
            <Stat key={key} value={value} label={t(`coordinator.${key}`)} tone={tone} />
          ))}
        </StatRow>
      )}

      {/* minmax(0, 1fr) tracks: a wide table scrolls inside its card instead of widening the page. */}
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        {isPending ? (
          <DashboardSummaryCardsSkeleton />
        ) : data ? (
          <>
            <TermCard term={data.term} step={data.next_step} isAdmin={user.is_admin} />
            {data.problems && data.term.year_id ? (
              <SetupProblemsCard
                problems={data.problems}
                yearId={data.term.year_id}
                isAdmin={user.is_admin}
              />
            ) : null}
            {data.completion && data.term.year_id ? (
              <CompletionCard
                completion={data.completion}
                yearId={data.term.year_id}
                isAdmin={user.is_admin}
              />
            ) : null}
            {data.completion && data.readiness.length ? (
              <ReadinessCard
                readiness={data.readiness}
                semesterNumber={data.completion.semester_number}
              />
            ) : null}
          </>
        ) : null}
        {user.is_admin ? <RecentChangesCard /> : null}
        <JobsCard />
      </div>
    </AdminPage>
  );
}
