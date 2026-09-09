import { usePrefetchSiblings } from "@flrc/ui/hooks/use-prefetch-siblings";
import { academicContextLabels } from "@flrc/i18n";
import {
  getGridOptions,
  getGridQueryKey,
  listAcademicYearsOptions,
  listClassCatalogOptions,
  undoGridMutation,
  type GridColumnOut,
} from "@flrc/api-client";
import { AcademicContextBar } from "@flrc/ui/components/academic-context-bar";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { ConfirmDialog } from "@flrc/ui/components/dialog";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Kbd, isMacPlatform } from "@flrc/ui/components/kbd";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { Segmented } from "@flrc/ui/components/segmented";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useBlocker } from "@tanstack/react-router";
import { CheckIcon, TriangleAlertIcon, Undo2Icon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ConflictDialog } from "../../grid/conflict-dialog";
import { useDirtyStore } from "../../grid/dirty-store";
import { GradeCell } from "../../grid/grade-cell";
import { GridTable } from "../../grid/grid-table";
import { OwnershipWarningDialog } from "../../grid/ownership-warning-dialog";
import { StepperView } from "../../grid/stepper";
import { useIsPhone } from "../../grid/use-is-phone";
import { useSaveGrid } from "../../grid/use-save-grid";

type Subject = "english" | "german" | "french";
type View = "auto" | "grid" | "stepper";

export const Route = createFileRoute("/_auth/classes/$classId/$subject")({
  validateSearch: (search: Record<string, unknown>) => ({
    semester:
      Number(search.semester) === 1 || Number(search.semester) === 2
        ? Number(search.semester)
        : undefined,
  }),
  component: GridPage,
});

function GridPage() {
  const { classId, subject: rawSubject } = Route.useParams();
  const { semester: requestedSemester } = Route.useSearch();
  const navigate = Route.useNavigate();
  const { user } = Route.useRouteContext();
  const subject = rawSubject as Subject;
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [ownershipColumns, setOwnershipColumns] = useState<GridColumnOut[]>([]);
  const ownershipSaveStarted = useRef(false);
  const [view, setView] = useState<View>("auto");
  const phone = useIsPhone();

  const queryOptions = {
    path: { class_id: Number(classId) },
    query: { subject, locale: i18n.language, semester: requestedSemester },
  };
  const gridKey = getGridQueryKey(queryOptions);
  const { data, isPending, isError } = useQuery(getGridOptions(queryOptions));
  const { data: years = [] } = useQuery(listAcademicYearsOptions());
  const { data: catalog = [] } = useQuery({
    ...listClassCatalogOptions({
      query: {
        year_id: data?.meta.year_id,
        semester: requestedSemester,
      },
    }),
    enabled: Boolean(data),
  });
  const dirtyCount = useDirtyStore((state) => Object.keys(state.cells).length);
  const save = useSaveGrid({ classId: Number(classId), subject, gridKey });

  useEffect(() => {
    if (ownershipColumns.length && save.isPending) ownershipSaveStarted.current = true;
    if (ownershipSaveStarted.current && !save.isPending) {
      ownershipSaveStarted.current = false;
      setOwnershipColumns([]);
    }
  }, [ownershipColumns.length, save.isPending]);

  const blocker = useBlocker({
    shouldBlockFn: () => Object.keys(useDirtyStore.getState().cells).length > 0,
    enableBeforeUnload: () => Object.keys(useDirtyStore.getState().cells).length > 0,
    withResolver: true,
  });

  useEffect(
    () => () => {
      useDirtyStore.getState().clearAll();
    },
    [classId, subject, requestedSemester],
  );

  const undo = useMutation({
    ...undoGridMutation(),
    onSuccess: () => {
      toast.success(t("grid.undoSuccess"));
      void queryClient.invalidateQueries({ queryKey: gridKey });
    },
  });

  const unownedColumns = useMemo(
    () => data?.columns.filter((column) => !column.owned_by_you) ?? [],
    [data?.columns],
  );
  const writable = data?.meta.semester_status === "open";
  const gradeTabs = useMemo(
    () =>
      data
        ? catalog.filter(
            (item) =>
              item.grade_level === data.meta.grade_level &&
              item.subjects.some((candidate) => candidate.subject === subject),
          )
        : [],
    [catalog, data, subject],
  );

  const prefetchBoard = useCallback(
    (targetClassId: number) =>
      queryClient.prefetchQuery({
        ...getGridOptions({
          path: { class_id: targetClassId },
          query: {
            subject,
            locale: i18n.language,
            semester: data?.meta.semester_number ?? requestedSemester,
          },
        }),
        staleTime: 30_000,
      }),
    [data?.meta.semester_number, i18n.language, queryClient, requestedSemester, subject],
  );

  usePrefetchSiblings(gradeTabs, prefetchBoard);

  const attemptSave = useCallback(() => {
    if (!writable) return;
    const dirtyColumnIds = new Set(
      Object.values(useDirtyStore.getState().cells).map((cell) => cell.columnId),
    );
    const affected = unownedColumns.filter((column) => dirtyColumnIds.has(column.id));
    if (affected.length) setOwnershipColumns(affected);
    else save.saveAll();
  }, [save, unownedColumns, writable]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "s") return;
      event.preventDefault();
      attemptSave();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [attemptSave]);

  if (isPending) return <PageSkeleton />;
  if (isError || !data) return <p className="text-sm text-destructive">{t("errors.load")}</p>;

  const showStepper = view === "stepper" || (view === "auto" && phone);
  const lastBatch = data.meta.my_last_batch;
  const isEmpty = data.columns.length === 0 || data.rows.length === 0;
  const saveKey = isMacPlatform() ? "⌘S" : "Ctrl+S";

  const goToBoard = (nextGrade: number, nextSubject: Subject) => {
    const target = catalog.find(
      (item) =>
        item.grade_level === nextGrade &&
        item.subjects.some((candidate) => candidate.subject === nextSubject),
    );
    if (!target) return;
    void navigate({
      to: "/classes/$classId/$subject",
      params: { classId: String(target.id), subject: nextSubject },
      search: { semester: data.meta.semester_number },
    });
  };

  const switchYear = async (nextYearId: number) => {
    const nextYear = years.find((item) => item.id === nextYearId);
    if (!nextYear) return;
    const nextSemester =
      nextYear.semesters.find((item) => item.number === data.meta.semester_number)?.number ??
      nextYear.semesters.find((item) => item.status === "open")?.number ??
      nextYear.semesters[0]?.number ??
      1;
    const nextCatalog = await queryClient.fetchQuery(
      listClassCatalogOptions({
        query: { year_id: nextYearId, semester: nextSemester },
      }),
    );
    const current = catalog.find((item) => item.id === Number(classId));
    const target =
      nextCatalog.find(
        (item) =>
          item.grade_level === data.meta.grade_level &&
          item.section === current?.section &&
          item.subjects.some((candidate) => candidate.subject === subject),
      ) ??
      nextCatalog.find(
        (item) =>
          item.grade_level === data.meta.grade_level &&
          item.subjects.some((candidate) => candidate.subject === subject),
      ) ??
      nextCatalog.find((item) => item.subjects.some((candidate) => candidate.subject === subject));
    if (!target) return;
    await navigate({
      to: "/classes/$classId/$subject",
      params: { classId: String(target.id), subject },
      search: { semester: nextSemester },
    });
  };

  return (
    <>
      <AcademicContextBar
        years={years}
        yearId={data.meta.year_id}
        semesterNumber={data.meta.semester_number}
        onYearChange={(next) => void switchYear(next)}
        onSemesterChange={(next) =>
          void navigate({
            to: "/classes/$classId/$subject",
            params: { classId, subject },
            search: { semester: next },
          })
        }
        labels={academicContextLabels(t, t("grid.locked"))}
      />

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 shadow-card lg:flex-row lg:items-center">
        <Segmented
          ariaLabel={t("classes.gradeLevel")}
          options={[1, 2, 3, 4, 5, 6, 7, 8].map((item) => ({
            value: item,
            label: String(item),
          }))}
          value={data.meta.grade_level}
          onChange={(next) => goToBoard(next, subject)}
          size="sm"
          className="max-w-full"
        />
        <Segmented
          ariaLabel={t("grid.subject")}
          options={(["english", "german", "french"] as const).map((item) => ({
            value: item,
            label: t(`subjects.${item}`),
          }))}
          value={subject}
          onChange={(next) => goToBoard(data.meta.grade_level, next)}
          size="sm"
          className="max-w-full"
        />
        <div className="flex min-w-0 flex-1 flex-wrap items-end gap-1 lg:justify-end">
          {gradeTabs.map((schoolClass) => (
            <button
              key={schoolClass.id}
              type="button"
              aria-current={schoolClass.id === Number(classId) ? "page" : undefined}
              className={[
                "min-w-0 flex-1 basis-16 rounded-lg px-2 py-2 text-xs font-semibold outline-none transition-colors sm:text-sm",
                schoolClass.id === Number(classId)
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              ].join(" ")}
              onPointerEnter={() => void prefetchBoard(schoolClass.id)}
              onFocus={() => void prefetchBoard(schoolClass.id)}
              onClick={() =>
                void navigate({
                  to: "/classes/$classId/$subject",
                  params: { classId: String(schoolClass.id), subject },
                  search: { semester: data.meta.semester_number },
                })
              }
            >
              {schoolClass.name}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="font-heading text-xl font-semibold tracking-tight">
            {data.meta.class_name}
            <span className="text-muted-foreground"> · </span>
            {t(`subjects.${data.meta.subject}`)}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("grid.rosterSummary", {
              students: data.rows.length,
              columns: data.columns.length,
            })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {writable ? null : <Badge tone="neutral">{t("grid.locked")}</Badge>}
          <Segmented
            ariaLabel={t("grid.viewLabel")}
            options={[
              { value: "grid", label: t("grid.gridView") },
              { value: "stepper", label: t("grid.stepperView") },
            ]}
            value={showStepper ? "stepper" : "grid"}
            onChange={(next) => setView(next)}
            size="sm"
          />
        </div>
      </div>

      {data.meta.grade_level === 4 &&
      subject !== "english" &&
      data.columns.every((column) => column.value_type === "scale3") ? (
        <p className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          {t("grid.gradeFourScaleOnly")}
        </p>
      ) : null}

      {unownedColumns.length > 0 && writable ? (
        <div className="flex gap-3 rounded-xl border border-warning/40 bg-warning-surface/60 px-4 py-3 text-sm">
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-warning" />
          <div>
            <p className="font-semibold">{t("grid.draftAccessTitle")}</p>
            <p className="mt-0.5 text-muted-foreground">
              {user.is_admin ? t("grid.adminDraftAccessBody") : t("grid.draftAccessBody")}
            </p>
          </div>
        </div>
      ) : null}

      {isEmpty ? (
        <EmptyState title={t("grid.emptyTitle")} description={t("grid.emptyBody")} />
      ) : showStepper ? (
        <StepperView
          data={data}
          renderCell={(column, row) => <GradeCell column={column} row={row} readOnly={!writable} />}
        />
      ) : (
        <GridTable
          key={`${classId}-${subject}-${data.meta.semester_number}`}
          data={data}
          readOnly={!writable}
        />
      )}

      {isEmpty ? null : (
        <div className="sticky bottom-4 z-30 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-card/95 px-4 py-2.5 shadow-raised backdrop-blur">
          <p className="flex items-center gap-2 text-sm font-medium">
            {dirtyCount > 0 ? (
              <>
                <span className="size-2 shrink-0 rounded-full bg-primary" />
                {t("grid.unsavedCount", { count: dirtyCount })}
              </>
            ) : (
              <>
                <CheckIcon className="size-4 shrink-0 text-success" />
                <span className="text-muted-foreground">{t("grid.allSaved")}</span>
              </>
            )}
          </p>

          {showStepper ? null : (
            <p className="hidden items-center gap-3 text-xs text-muted-foreground xl:flex">
              <span className="flex items-center gap-1.5">
                <Kbd>↑</Kbd>
                <Kbd>↓</Kbd>
                <Kbd>←</Kbd>
                <Kbd>→</Kbd>
                {t("grid.keyMove")}
              </span>
              <span className="flex items-center gap-1.5">
                <Kbd>{t("grid.keyEnter")}</Kbd>
                {t("grid.keyNextRow")}
              </span>
            </p>
          )}

          <div className="ml-auto flex items-center gap-2">
            {lastBatch?.undoable ? (
              <Button
                variant="outline"
                size="sm"
                pending={undo.isPending}
                pendingLabel={t("feedback.working")}
                onClick={() => undo.mutate({ path: { class_id: Number(classId) } })}
              >
                <Undo2Icon />
                {t("grid.undoLast", { count: lastBatch.cell_count })}
              </Button>
            ) : null}
            <Button
              data-testid="save-grid"
              onClick={attemptSave}
              disabled={dirtyCount === 0 || !writable}
              pending={save.isPending}
              pendingLabel={t("grid.saving")}
            >
              {save.savedFlash
                ? t("grid.saved")
                : dirtyCount > 0
                  ? t("grid.saveAll", { count: dirtyCount })
                  : t("forms.save")}
              {dirtyCount > 0 && !save.isPending ? (
                <Kbd className="hidden border-primary-foreground/25 bg-primary-foreground/15 text-primary-foreground sm:inline-flex">
                  {saveKey}
                </Kbd>
              ) : null}
            </Button>
          </div>
        </div>
      )}

      <ConflictDialog
        conflicts={save.conflicts}
        pending={save.isPending}
        onAccept={save.acceptConflicts}
        onCancel={save.cancelConflicts}
      />
      <OwnershipWarningDialog
        columns={ownershipColumns}
        isAdmin={user.is_admin}
        pending={save.isPending}
        onClose={() => setOwnershipColumns([])}
        onAccept={() => save.saveAll(true)}
      />
      <ConfirmDialog
        open={blocker.status === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.status === "blocked") blocker.reset();
        }}
        title={t("grid.unsavedTitle")}
        description={t("grid.unsavedLeave")}
        cancelLabel={t("forms.cancel")}
        confirmLabel={t("grid.discardChanges")}
        destructive
        onConfirm={() => {
          if (blocker.status !== "blocked") return;
          useDirtyStore.getState().clearAll();
          blocker.proceed();
        }}
      />
    </>
  );
}
