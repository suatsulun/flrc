import { getClassSheetOptions, listClassCatalogOptions } from "@flrc/api-client";
import { Button, buttonVariants } from "@flrc/ui/components/button";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  DownloadIcon,
  FileTextIcon,
  FilesIcon,
  PrinterIcon,
  TablePropertiesIcon,
  UsersRoundIcon,
} from "lucide-react";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useClassSheetPdf } from "../../class-report/class-sheet-pdf";
import { ClassSheetTable } from "../../class-report/class-sheet-table";
import { REPORT_GRADES, reportClasses } from "../../class-report/scope";
import { BoardSwitcher } from "../../grid/board-switcher";

export const Route = createFileRoute("/_auth/class-report/$classId")({
  validateSearch: (search: Record<string, unknown>) => ({
    semester:
      Number(search.semester) === 1 || Number(search.semester) === 2
        ? Number(search.semester)
        : undefined,
  }),
  component: ClassReportPage,
});

/** A file name people recognise in their downloads: `class-report-5-A-s1.pdf`. */
function fileName(...parts: Array<string | number>) {
  return `${parts.join("-").replace(/[\\/:*?"<>|\s]+/g, "-")}.pdf`;
}

/** The machine code of an API error body, such as `{"detail": {"code": "…"}}`. */
function errorCode(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const { detail } = error;
  return typeof detail === "object" && detail !== null && "code" in detail
    ? String(detail.code)
    : undefined;
}

function ClassReportPage() {
  const { classId } = Route.useParams();
  const { semester: requestedSemester } = Route.useSearch();
  const navigate = Route.useNavigate();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const pdf = useClassSheetPdf();

  const { data, isPending, isError, error } = useQuery(
    getClassSheetOptions({
      path: { class_id: Number(classId) },
      query: { semester: requestedSemester },
    }),
  );
  // The board switcher reads the same catalog entry, so this costs no extra request.
  const { data: catalog = [] } = useQuery({
    ...listClassCatalogOptions({
      query: { year_id: data?.year_id, semester: requestedSemester },
    }),
    enabled: Boolean(data),
  });

  const prefetchBoard = useCallback(
    (targetClassId: number) =>
      queryClient.prefetchQuery({
        ...getClassSheetOptions({
          path: { class_id: targetClassId },
          query: { semester: data?.semester_number ?? requestedSemester },
        }),
        staleTime: 30_000,
      }),
    [data?.semester_number, queryClient, requestedSemester],
  );

  if (isPending) return <PageSkeleton />;
  if (isError) {
    return errorCode(error) === "class_report_middle_english_only" ? (
      <EmptyState
        icon={<FileTextIcon />}
        title={t("classReport.unavailableTitle")}
        description={t("classReport.unavailableBody")}
      />
    ) : (
      <p className="text-sm text-destructive">{t("errors.load")}</p>
    );
  }

  // The teacher's own middle-school English classes this semester, in catalog order.
  const myClassIds = reportClasses(catalog, { mine: true })
    .filter((schoolClass) =>
      schoolClass.subjects.some((entry) => entry.subject === "english" && entry.student_count > 0),
    )
    .map((schoolClass) => schoolClass.id);
  const empty = data.students.length === 0;
  const busy = pdf.pending !== null;

  return (
    <div className="space-y-4">
      <BoardSwitcher
        classId={classId}
        subject="english"
        requestedSemester={requestedSemester}
        meta={data}
        grades={REPORT_GRADES}
        subjects={["english"]}
        compact={false}
        lockedLabel={t("classWorkspace.readOnly")}
        goTo={(targetClassId, _subject, semester) =>
          navigate({
            to: "/class-report/$classId",
            params: { classId: String(targetClassId) },
            search: { semester },
          })
        }
        prefetchBoard={prefetchBoard}
      />

      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            {t("classReport.title")}
          </p>
          <h1 className="font-heading text-xl font-semibold tracking-tight">
            {data.class_name}
            <span className="text-muted-foreground"> · </span>
            {t("subjects.english")}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {[
              data.year_label,
              t("classReport.semester", { number: data.semester_number }),
              t("classReport.students", { count: data.students.length }),
            ].join(" · ")}
            {data.teachers.length ? (
              <>
                {" · "}
                {t(data.teachers.length === 1 ? "classReport.teacher" : "classReport.teachers", {
                  names: data.teachers.join(", "),
                })}
              </>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/classes/$classId/$subject"
            params={{ classId, subject: "english" }}
            search={{ semester: data.semester_number }}
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            <TablePropertiesIcon />
            {t("classReport.backToTable")}
          </Link>
          {myClassIds.length ? (
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              pending={pdf.pending === "mine"}
              pendingLabel={t("feedback.working")}
              onClick={() =>
                pdf.download(
                  "mine",
                  data.semester_id,
                  myClassIds,
                  fileName("class-reports", data.year_label, `s${data.semester_number}`),
                )
              }
            >
              <FilesIcon />
              {t("classReport.allMine", { count: myClassIds.length })}
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            disabled={busy || empty}
            pending={pdf.pending === "print"}
            pendingLabel={t("feedback.working")}
            onClick={() => pdf.print(data.semester_id, [data.class_id])}
          >
            <PrinterIcon />
            {t("classReport.print")}
          </Button>
          <Button
            size="sm"
            disabled={busy || empty}
            pending={pdf.pending === "download"}
            pendingLabel={t("feedback.working")}
            onClick={() =>
              pdf.download(
                "download",
                data.semester_id,
                [data.class_id],
                fileName("class-report", data.class_name, `s${data.semester_number}`),
              )
            }
          >
            <DownloadIcon />
            {t("classReport.download")}
          </Button>
        </div>
      </div>

      {empty ? (
        <EmptyState
          icon={<UsersRoundIcon />}
          title={t("classReport.emptyTitle")}
          description={t("classReport.emptyBody")}
        />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">{t("classReport.readingHint")}</p>
          <ClassSheetTable sheet={data} />
          <p className="text-xs text-muted-foreground">{t("classReport.privacyNote")}</p>
        </>
      )}
    </div>
  );
}
