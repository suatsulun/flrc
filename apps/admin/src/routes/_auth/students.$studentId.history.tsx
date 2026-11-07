import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { ArrowLeftIcon } from "lucide-react";
import { getStudentHistoryOptions, type HistoryYear } from "@flrc/api-client";
import { academicContextLabels } from "@flrc/i18n";
import { AcademicContextBar } from "@flrc/ui/components/academic-context-bar";
import { Badge } from "@flrc/ui/components/badge";
import {
  Card,
  CardBody,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
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
import { StudentHistorySkeleton } from "../../admin/page-skeletons";

/** The year and semester on screen; absent values fall back to the latest recorded term. */
type HistorySearch = { year?: number; semester?: 1 | 2 };

function positiveId(value: unknown): number | undefined {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : undefined;
}

export const Route = createFileRoute("/_auth/students/$studentId/history")({
  validateSearch: (search: Record<string, unknown>): HistorySearch => ({
    year: positiveId(search.year),
    semester:
      Number(search.semester) === 1 || Number(search.semester) === 2
        ? (Number(search.semester) as 1 | 2)
        : undefined,
  }),
  component: StudentHistoryPage,
});

/**
 * The semester a year opens on: the open one while it has grades, else the latest with grades,
 * else the open one, else the first.
 */
function defaultSemester(year: HistoryYear) {
  const open = year.semesters.find((term) => term.status === "open");
  if (open?.cells.length) return open.number;
  const recorded = year.semesters.filter((term) => term.cells.length > 0);
  return (recorded.at(-1) ?? open ?? year.semesters[0])?.number;
}

function StudentHistoryPage() {
  const { studentId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const { t } = useTranslation();
  const { data, isPending, isError } = useQuery(
    getStudentHistoryOptions({ path: { student_id: Number(studentId) } }),
  );

  if (isPending) return <StudentHistorySkeleton />;
  if (isError || !data) return <EmptyState title={t("errors.load")} />;

  // Years arrive oldest first; without a choice the most recent year with grades is shown.
  const selectedYear =
    data.years.find((year) => year.year_id === search.year) ??
    data.years.filter((year) => year.semesters.some((term) => term.cells.length > 0)).at(-1) ??
    data.years.at(-1);
  const semesterNumber =
    selectedYear?.semesters.find((term) => term.number === search.semester)?.number ??
    (selectedYear ? defaultSemester(selectedYear) : undefined);
  const term = selectedYear?.semesters.find((item) => item.number === semesterNumber);
  const select = (next: HistorySearch) =>
    void navigate({ search: (previous) => ({ ...previous, ...next }), replace: true });

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
            title={data.full_name}
            description={t("students.description")}
            meta={<Badge tone="neutral">{t("archive.readOnly")}</Badge>}
          />
        </div>
      </div>

      {!selectedYear ? (
        <EmptyState title={t("students.noHistory")} />
      ) : (
        <>
          <AcademicContextBar
            years={data.years.map((year) => ({
              id: year.year_id,
              label: year.label,
              status: year.year_status,
              semesters: year.semesters.map((item) => ({
                id: item.number,
                number: item.number,
                status: item.status,
              })),
            }))}
            yearId={selectedYear.year_id}
            semesterNumber={semesterNumber ?? 1}
            onYearChange={(year) => select({ year, semester: undefined })}
            onSemesterChange={(semester) =>
              select({ year: selectedYear.year_id, semester: semester === 2 ? 2 : 1 })
            }
            labels={academicContextLabels(t, t("lifecycle.locked"))}
          />

          <Card>
            <CardHeader>
              <div className="min-w-0">
                <CardTitle className="text-base">
                  {selectedYear.class_name ?? "—"}
                  <span className="font-normal text-muted-foreground">
                    {" · "}
                    {t("students.schoolNumber")} {selectedYear.school_number ?? "—"}
                  </span>
                </CardTitle>
                <CardDescription>
                  {selectedYear.label}
                  {term ? ` · ${t("lifecycle.semester", { number: term.number })}` : null}
                </CardDescription>
              </div>
              {selectedYear.language ? (
                <Badge tone="outline">{t(`subjects.${selectedYear.language}`)}</Badge>
              ) : null}
            </CardHeader>
            {!term ? (
              <CardContent>
                <EmptyState
                  className="border-0 bg-transparent py-8"
                  title={t("students.historyNoSemesters")}
                />
              </CardContent>
            ) : term.cells.length === 0 ? (
              <CardContent>
                <EmptyState
                  className="border-0 bg-transparent py-8"
                  title={t("students.historyEmptySemester")}
                  description={
                    term.status === "open"
                      ? t("students.historyEmptyOpen")
                      : t("students.historyEmptyClosed")
                  }
                />
              </CardContent>
            ) : (
              <CardBody>
                <TableScroll
                  aria-label={t("students.historyTableLabel", { semester: term.number })}
                >
                  {/* Fixed layout so a long field name or comment truncates inside the card
                      instead of widening the table past a phone screen. */}
                  <Table className="table-fixed">
                    <colgroup>
                      <col />
                      <col className="w-28 sm:w-2/5" />
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
                              <TableText className="ml-auto max-w-full">
                                {String(cell.value)}
                              </TableText>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableScroll>
              </CardBody>
            )}
          </Card>
        </>
      )}
    </>
  );
}
