import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { HistoryIcon, SchoolIcon } from "lucide-react";
import {
  listAdminClassesOptions,
  listStudents,
  listStudentsInfiniteQueryKey,
  listYearsOptions,
} from "@flrc/api-client";
import { Button, buttonVariants } from "@flrc/ui/components/button";
import { Card, CardBody, CardHeader } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
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
  TableText,
} from "@flrc/ui/components/table";
import { AdminPage } from "../../admin/AdminPage";
import { useDebouncedValue } from "../../students/use-debounced-value";

const PAGE_SIZE = 50;

/**
 * Whole-year student search by name or school number.
 *
 * Index-only: as a layout route this would swallow `/students/$id/history`.
 */
export const Route = createFileRoute("/_auth/students/")({ component: StudentSearchPage });

function StudentSearchPage() {
  const { t } = useTranslation();
  const {
    data: years = [],
    isPending: yearsPending,
    isError: yearsError,
  } = useQuery(listYearsOptions());
  const [yearId, setYearId] = useState<number>();
  const year =
    years.find((item) => item.id === yearId) ??
    years.find((item) => item.status === "active") ??
    years[0];
  const [text, setText] = useState("");
  const q = useDebouncedValue(text.trim());
  const query = { q, year_id: year?.id, limit: PAGE_SIZE };

  const students = useInfiniteQuery({
    queryKey: listStudentsInfiniteQueryKey({ query }),
    queryFn: async ({ pageParam, signal }) => {
      const result = await listStudents({ query: { ...query, cursor: pageParam }, signal });
      if (result.error) throw result.error;
      if (!result.data) throw new Error("students_unavailable");
      return result.data;
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: Boolean(year),
    placeholderData: keepPreviousData,
  });
  const { data: classes = [], isError: classesError } = useQuery({
    ...listAdminClassesOptions({ path: { year_id: year?.id ?? 0 } }),
    enabled: Boolean(year),
  });
  const classById = new Map(classes.map((item) => [item.id, item]));
  const items = students.data?.pages.flatMap((page) => page.items) ?? [];

  if (yearsPending) return <PageSkeleton />;
  if (yearsError || classesError || students.isError) {
    return <EmptyState title={t("errors.load")} />;
  }

  return (
    <AdminPage title={t("students.title")} description={t("studentSearch.description")}>
      {!year ? (
        <EmptyState title={t("studentSearch.noYear")} />
      ) : (
        <Card>
          <CardHeader className="flex-col items-stretch sm:flex-row sm:items-center">
            <Input
              className="w-full sm:max-w-sm"
              type="search"
              value={text}
              aria-label={t("studentSearch.searchLabel")}
              placeholder={t("studentSearch.placeholder")}
              onChange={(event) => setText(event.currentTarget.value)}
            />
            <NativeSelect
              className="w-full sm:w-48"
              aria-label={t("reports.yearLabel")}
              value={year.id}
              onChange={(event) => setYearId(Number(event.target.value))}
            >
              {years.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} · {t(`lifecycle.${item.status}`)}
                </option>
              ))}
            </NativeSelect>
          </CardHeader>
          <CardBody>
            <TableScroll aria-label={t("studentSearch.tableLabel")}>
              <Table className="min-w-[40rem]">
                <TableCaption>{t("studentSearch.tableLabel")}</TableCaption>
                <TableHead>
                  <tr>
                    <TableHeader className="sticky left-0 z-30 min-w-56 border-r bg-muted/95">
                      {t("audit.student")}
                    </TableHeader>
                    <TableHeader className="w-28">{t("studentSearch.class")}</TableHeader>
                    <TableHeader className="w-64">
                      <span className="sr-only">{t("students.actions")}</span>
                    </TableHeader>
                  </tr>
                </TableHead>
                <TableBody>
                  {students.isPending ? (
                    <TableEmpty colSpan={3}>{t("loading")}</TableEmpty>
                  ) : items.length === 0 ? (
                    <TableEmpty colSpan={3}>{t("students.empty")}</TableEmpty>
                  ) : (
                    items.map((student) => {
                      const schoolClass = classById.get(student.class_id);
                      return (
                        <TableRow key={student.id}>
                          <TableCell className="sticky left-0 z-10 border-r bg-card group-even:bg-muted group-hover:bg-accent">
                            <span className="flex items-baseline gap-2">
                              <span className="tabular w-12 shrink-0 text-xs text-muted-foreground">
                                {student.school_number ?? "—"}
                              </span>
                              <TableText className="max-w-56 font-medium">
                                {student.full_name}
                              </TableText>
                            </span>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {schoolClass?.name ?? "—"}
                          </TableCell>
                          <TableCell align="right">
                            <span className="flex justify-end gap-1.5">
                              <Link
                                to="/students/$studentId/history"
                                params={{ studentId: String(student.id) }}
                                className={buttonVariants({ variant: "ghost", size: "sm" })}
                              >
                                <HistoryIcon />
                                {t("students.history")}
                              </Link>
                              {schoolClass ? (
                                <Link
                                  to="/classes"
                                  search={{
                                    year: year.id,
                                    grade: schoolClass.grade_level,
                                    class: schoolClass.id,
                                  }}
                                  className={buttonVariants({ variant: "ghost", size: "sm" })}
                                >
                                  <SchoolIcon />
                                  {t("studentSearch.openClass")}
                                </Link>
                              ) : null}
                            </span>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </TableScroll>
          </CardBody>
        </Card>
      )}

      {students.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            pending={students.isFetchingNextPage}
            pendingLabel={t("loading")}
            onClick={() => void students.fetchNextPage()}
          >
            {t("audit.loadMore")}
          </Button>
        </div>
      ) : null}
    </AdminPage>
  );
}
