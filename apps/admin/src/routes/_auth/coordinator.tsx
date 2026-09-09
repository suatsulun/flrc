import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { coordinatorCompletenessOptions, coordinatorOverviewOptions } from "@flrc/api-client";
import { Card, CardBody } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { Stat } from "@flrc/ui/components/stat";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
  TableScroll,
} from "@flrc/ui/components/table";
import { AdminPage } from "../../admin/AdminPage";

export const Route = createFileRoute("/_auth/coordinator")({ component: CoordinatorPage });

function CoordinatorPage() {
  const { t } = useTranslation();
  const {
    data: overview,
    isPending: overviewPending,
    isError: overviewError,
  } = useQuery(coordinatorOverviewOptions());
  const semesterId = overview?.semester_id ?? undefined;
  const completenessOptions = coordinatorCompletenessOptions({
    query: { semester_id: semesterId ?? 0 },
  });
  const {
    data: rows = [],
    isPending: rowsPending,
    isError: rowsError,
  } = useQuery({
    ...completenessOptions,
    enabled: semesterId !== undefined,
  });

  const stats = overview
    ? ([
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
      ] as const)
    : [];

  if (overviewError || rowsError) {
    return <EmptyState title={t("errors.load")} />;
  }
  if (overviewPending || (semesterId !== undefined && rowsPending)) return <PageSkeleton />;

  return (
    <AdminPage
      title={t("coordinator.title")}
      description={t("coordinator.description", {
        year: overview?.year_label ?? "—",
        semester: overview?.semester_number ?? "—",
      })}
    >
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {stats.map(([key, value, tone]) => (
          <Stat key={key} value={value} label={t(`coordinator.${key}`)} tone={tone} />
        ))}
      </div>

      <Card>
        <CardBody>
          <TableScroll aria-label={t("coordinator.tableLabel")}>
            <Table className="min-w-[48rem]">
              <TableCaption>{t("coordinator.tableLabel")}</TableCaption>
              <TableHead>
                <tr>
                  <TableHeader className="sticky left-0 z-30 min-w-32 border-r bg-muted/95">
                    {t("classes.title")}
                  </TableHeader>
                  <TableHeader className="min-w-32">{t("grid.subject")}</TableHeader>
                  <TableHeader className="w-24" align="right">
                    {t("coordinator.expected")}
                  </TableHeader>
                  <TableHeader className="w-24" align="right">
                    {t("coordinator.filled")}
                  </TableHeader>
                  <TableHeader className="w-24" align="right">
                    {t("coordinator.missing")}
                  </TableHeader>
                  <TableHeader className="w-56">{t("coordinator.completion")}</TableHeader>
                </tr>
              </TableHead>
              <TableBody>
                {rows.length === 0 ? (
                  <TableEmpty colSpan={6}>{t("coordinator.empty")}</TableEmpty>
                ) : (
                  rows.map((row) => (
                    <TableRow key={`${row.class_id}-${row.subject}`}>
                      <TableCell className="sticky left-0 z-10 border-r bg-card font-medium group-even:bg-muted group-hover:bg-accent">
                        {row.class_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {t(`subjects.${row.subject}`)}
                      </TableCell>
                      <TableCell align="right">{row.expected_cells}</TableCell>
                      <TableCell align="right">{row.filled_cells}</TableCell>
                      <TableCell
                        align="right"
                        className={row.missing_cells > 0 ? "font-medium text-warning" : undefined}
                      >
                        {row.missing_cells}
                      </TableCell>
                      <TableCell>
                        {/* Nothing expected means nothing to complete — a full
                            green bar there would read as a false all-clear. */}
                        {row.expected_cells === 0 ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <span className="flex items-center gap-2.5">
                            <span
                              className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
                              role="img"
                              aria-label={`${row.percent.toFixed(0)}%`}
                            >
                              <span
                                className={`block h-full rounded-full ${
                                  row.percent >= 99.5 ? "bg-success" : "bg-primary"
                                }`}
                                style={{ width: `${Math.min(row.percent, 100)}%` }}
                              />
                            </span>
                            <span className="tabular w-12 shrink-0 text-right text-xs text-muted-foreground">
                              {row.percent.toFixed(1)}%
                            </span>
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableScroll>
        </CardBody>
      </Card>
    </AdminPage>
  );
}
