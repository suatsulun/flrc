import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { ArrowLeftIcon } from "lucide-react";
import { getStudentHistoryOptions } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { PageHeader } from "@flrc/ui/components/page-header";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableScroll,
  TableText,
} from "@flrc/ui/components/table";

export const Route = createFileRoute("/_auth/students/$studentId/history")({
  component: StudentHistoryPage,
});

function StudentHistoryPage() {
  const { studentId } = Route.useParams();
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery(
    getStudentHistoryOptions({ path: { student_id: Number(studentId) } }),
  );

  if (isPending) return <PageSkeleton />;
  if (isError || !data) return <EmptyState title={t("errors.load")} />;

  return (
    <>
      <div>
        <Link
          to="/students"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeftIcon className="size-3.5" />
          {t("students.title")}
        </Link>
        <div className="mt-1.5">
          <PageHeader
            title={data?.full_name ?? t("students.history")}
            description={t("students.description")}
            meta={<Badge tone="neutral">{t("archive.readOnly")}</Badge>}
          />
        </div>
      </div>

      {data && data.years.length === 0 ? (
        <EmptyState title={t("students.noHistory")} />
      ) : (
        data?.years.map((year) => (
          <Card key={year.year_id}>
            <CardHeader>
              <div>
                <CardTitle className="text-base">
                  {year.label}
                  <span className="font-normal text-muted-foreground">
                    {" · "}
                    {year.class_name ?? "—"}
                    {" · "}
                    {t("students.schoolNumber")} {year.school_number ?? "—"}
                  </span>
                </CardTitle>
              </div>
              {year.language ? (
                <Badge tone="outline">{t(`subjects.${year.language}`)}</Badge>
              ) : null}
            </CardHeader>
            <CardContent className="grid gap-4 lg:grid-cols-2">
              {year.semesters.map((term) => (
                // `min-w-0` keeps a long criterion label from widening the
                // grid track and pushing the page into horizontal scroll.
                <section key={term.number} className="min-w-0">
                  <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    {t("lifecycle.semester", { number: term.number })}
                  </h3>
                  {term.cells.length === 0 ? (
                    <p className="rounded-lg bg-muted/60 px-3 py-6 text-center text-sm text-muted-foreground">
                      {t("archive.empty")}
                    </p>
                  ) : (
                    <div className="min-w-0 overflow-hidden rounded-lg border border-border">
                      <TableScroll
                        aria-label={t("students.historyTableLabel", { semester: term.number })}
                      >
                        {/* Fixed layout so a long criterion label truncates
                            inside the card instead of widening the table. */}
                        <Table className="w-full table-fixed">
                          <colgroup>
                            <col />
                            <col style={{ width: "8rem" }} />
                          </colgroup>
                          <TableCaption>
                            {t("students.historyTableLabel", { semester: term.number })}
                          </TableCaption>
                          <TableHead>
                            <tr>
                              <TableHeader>{t("audit.column")}</TableHeader>
                              <TableHeader align="right">{t("forms.value")}</TableHeader>
                            </tr>
                          </TableHead>
                          <TableBody>
                            {term.cells.map((cell) => (
                              <TableRow key={cell.column_id}>
                                <TableCell className="overflow-hidden">
                                  <span className="flex min-w-0 items-baseline gap-1.5">
                                    <TableText className="max-w-full">{cell.label}</TableText>
                                    <span className="truncate text-xs text-muted-foreground">
                                      {t(`subjects.${cell.subject}`)}
                                    </span>
                                  </span>
                                </TableCell>
                                <TableCell align="right" className="font-medium">
                                  {cell.value === null || cell.value === "" ? (
                                    <span className="text-muted-foreground">—</span>
                                  ) : (
                                    // Comment columns hold whole sentences.
                                    <TableText className="max-w-full">
                                      {String(cell.value)}
                                    </TableText>
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableScroll>
                    </div>
                  )}
                </section>
              ))}
            </CardContent>
          </Card>
        ))
      )}
    </>
  );
}
