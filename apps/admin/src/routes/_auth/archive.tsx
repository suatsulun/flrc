import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getArchiveGridOptions,
  listArchiveClassesOptions,
  listArchiveYearsOptions,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Card, CardBody } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
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
import { AdminPage } from "../../admin/AdminPage";

export const Route = createFileRoute("/_auth/archive")({ component: ArchivePage });

function ArchivePage() {
  const { t } = useTranslation();
  const {
    data: years = [],
    isPending: yearsPending,
    isError: yearsError,
  } = useQuery(listArchiveYearsOptions());
  const [yearId, setYearId] = useState<number>();
  const selectedYearId = yearId ?? years[0]?.id;
  const classOptions = listArchiveClassesOptions({ path: { year_id: selectedYearId ?? 0 } });
  const {
    data: classes = [],
    isPending: classesPending,
    isError: classesError,
  } = useQuery({
    ...classOptions,
    enabled: selectedYearId !== undefined,
  });
  const [classId, setClassId] = useState<number>();
  const selectedClassId = classId ?? classes[0]?.id;
  const [semester, setSemester] = useState(1);
  const [subject, setSubject] = useState<"english" | "german" | "french">("english");
  const gridOptions = getArchiveGridOptions({
    path: { class_id: selectedClassId ?? 0 },
    query: { semester, subject },
  });
  const {
    data: grid,
    isPending: gridPending,
    isError: gridError,
  } = useQuery({ ...gridOptions, enabled: selectedClassId !== undefined });

  if (yearsError || classesError || gridError) return <EmptyState title={t("errors.load")} />;
  if (
    yearsPending ||
    (selectedYearId !== undefined && classesPending) ||
    (selectedClassId !== undefined && gridPending)
  ) {
    return <PageSkeleton />;
  }

  return (
    <AdminPage
      title={t("archive.title")}
      description={t("archive.description")}
      meta={<Badge tone="neutral">{t("archive.readOnly")}</Badge>}
      actions={
        <>
          <NativeSelect
            className="w-36"
            aria-label={t("reports.yearLabel")}
            value={selectedYearId ?? ""}
            onChange={(event) => {
              setYearId(Number(event.target.value));
              setClassId(undefined);
            }}
          >
            {years.map((year) => (
              <option key={year.id} value={year.id}>
                {year.label}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            className="w-28"
            aria-label={t("classes.title")}
            value={selectedClassId ?? ""}
            onChange={(event) => setClassId(Number(event.target.value))}
          >
            {classes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            className="w-32"
            aria-label={t("lifecycle.semester", { number: semester })}
            value={semester}
            onChange={(event) => setSemester(Number(event.target.value))}
          >
            <option value={1}>{t("lifecycle.semester", { number: 1 })}</option>
            <option value={2}>{t("lifecycle.semester", { number: 2 })}</option>
          </NativeSelect>
          <NativeSelect
            className="w-32"
            aria-label={t("grid.subject")}
            value={subject}
            onChange={(event) => setSubject(event.target.value as typeof subject)}
          >
            {(["english", "german", "french"] as const).map((item) => (
              <option key={item} value={item}>
                {t(`subjects.${item}`)}
              </option>
            ))}
          </NativeSelect>
        </>
      }
    >
      {!grid || grid.rows.length === 0 ? (
        <EmptyState title={t("archive.empty")} description={t("archive.emptyBody")} />
      ) : (
        <Card>
          <CardBody>
            <TableScroll aria-label={t("archive.tableLabel")}>
              <Table style={{ minWidth: `${14 + grid.columns.length * 10}rem` }}>
                <TableCaption>{t("archive.tableLabel")}</TableCaption>
                <TableHead>
                  <tr>
                    <TableHeader className="sticky left-0 z-30 min-w-56 border-r bg-muted/95">
                      {t("students.fullName")}
                    </TableHeader>
                    {grid.columns.map((column) => (
                      <TableHeader key={column.id} align="center" className="w-40">
                        {/* Assessment labels are whole criterion sentences; an
                            unclamped one would stretch the column past 40rem. */}
                        <TableText className="mx-auto max-w-40 normal-case">
                          {column.label}
                        </TableText>
                      </TableHeader>
                    ))}
                  </tr>
                </TableHead>
                <TableBody>
                  {grid.rows.map((row) => (
                    <TableRow key={row.student_id}>
                      <TableCell className="sticky left-0 z-10 min-w-56 border-r bg-card font-medium group-even:bg-muted group-hover:bg-accent">
                        <span className="mr-2 tabular text-xs text-muted-foreground">
                          {row.school_number ?? "—"}
                        </span>
                        <TableText className="inline-block max-w-56 align-middle">
                          {row.full_name}
                        </TableText>
                      </TableCell>
                      {grid.columns.map((column) => (
                        <TableCell key={column.id} align="center">
                          {row.cells[String(column.id)] ?? (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableScroll>
          </CardBody>
        </Card>
      )}
    </AdminPage>
  );
}
