import { usePrefetchSiblings } from "@flrc/ui/hooks/use-prefetch-siblings";
import { GRADES, academicContextLabels, gradeTabLabel } from "@flrc/i18n";
import type { ColumnCreate } from "@flrc/api-client";
import {
  createAdminClassMutation,
  getAdminRosterOptions,
  listAdminClassesOptions,
  listColumnsOptions,
  listYearsOptions,
  moveAdminRosterMutation,
} from "@flrc/api-client";
import { AcademicContextBar } from "@flrc/ui/components/academic-context-bar";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Input } from "@flrc/ui/components/input";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { Segmented } from "@flrc/ui/components/segmented";
import { useDragPageAutoScroll } from "@flrc/ui/hooks/use-drag-page-auto-scroll";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { PlusIcon } from "lucide-react";
import { useCallback, useMemo, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AdminPage } from "../../admin/AdminPage";
import { ClassActions } from "../../admin/ClassActions";
import { ClassAddColumn } from "../../admin/ClassAddColumn";
import { ClassRemovePanel } from "../../admin/ClassRemovePanel";
import { ClassRosterTable } from "../../admin/ClassRosterTable";
import { ClassTeachers } from "../../admin/ClassTeachers";
import { MoveStudentsDialog, type MoveRequest } from "../../admin/MoveStudentsDialog";
import { moveConfirmationSkipped } from "../../admin/move-confirmation";
import { useNotifyDone } from "../../admin/undo-toast";
import { useRefreshQueries } from "../../admin/use-refresh-queries";

const SUBJECTS = ["english", "german", "french"] as const;
type Subject = (typeof SUBJECTS)[number];
type Role = ColumnCreate["owner_role"];

/**
 * Optional deep link into the workspace (dashboard and student search): the year, grade, class
 * tab and subject to show. The URL follows the admin's own choices, so a reload keeps them.
 */
export type ClassWorkspaceSearch = {
  year?: number;
  grade?: number;
  class?: number;
  subject?: Subject;
};

function positiveId(value: unknown): number | undefined {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : undefined;
}

export const Route = createFileRoute("/_auth/classes")({
  validateSearch: (search: Record<string, unknown>): ClassWorkspaceSearch => ({
    year: positiveId(search.year),
    grade:
      search.grade != null && GRADES.includes(Number(search.grade))
        ? Number(search.grade)
        : undefined,
    class: positiveId(search.class),
    subject: SUBJECTS.includes(search.subject as Subject) ? (search.subject as Subject) : undefined,
  }),
  component: ClassesPage,
});

function ClassesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const invalidate = useRefreshQueries();
  const notifyDone = useNotifyDone();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const updateSearch = (next: ClassWorkspaceSearch) =>
    void navigate({ search: (previous) => ({ ...previous, ...next }), replace: true });
  const yearId = search.year;
  const grade = search.grade ?? 5;
  const subject = search.subject ?? "english";
  const classId = search.class;
  const [chosenColumnOwner, setColumnOwner] = useState<Role>("main");
  // A new field's owner must fit the subject, also when the URL changes the subject.
  const columnOwner: Role =
    subject !== "english" ? subject : chosenColumnOwner === "skills" ? "skills" : "main";
  const {
    data: years = [],
    isPending: yearsPending,
    isError: yearsError,
  } = useQuery(listYearsOptions());
  const selectedYear =
    years.find((item) => item.id === yearId) ??
    years.find((item) => item.status === "active") ??
    years[0];
  // Until the admin picks one, the open semester (else the first) is shown.
  const [semesterNumber, setSemesterNumber] = useState<number>();
  const selectedSemester =
    selectedYear?.semesters.find((item) => item.number === semesterNumber) ??
    selectedYear?.semesters.find((item) => item.status === "open") ??
    selectedYear?.semesters[0];

  const [draggedStudentId, setDraggedStudentId] = useState<number>();
  const [mode, setMode] = useState<"table" | "remove">("table");
  useDragPageAutoScroll(Boolean(draggedStudentId));

  const {
    data: classes = [],
    isPending: classesPending,
    isError: classesError,
  } = useQuery({
    ...listAdminClassesOptions({ path: { year_id: selectedYear?.id ?? 0 } }),
    enabled: Boolean(selectedYear),
  });
  const gradeClasses = useMemo(
    () => classes.filter((item) => item.grade_level === grade),
    [classes, grade],
  );
  const selectedClass = gradeClasses.find((item) => item.id === classId) ?? gradeClasses[0];

  const {
    data: roster = [],
    isPending: rosterPending,
    isError: rosterError,
  } = useQuery({
    ...getAdminRosterOptions({ path: { class_id: selectedClass?.id ?? 0 } }),
    enabled: Boolean(selectedClass),
  });
  const { data: columns = [], isError: columnsError } = useQuery({
    ...listColumnsOptions({
      query: {
        grade_level: grade,
        subject,
        semester_id: selectedSemester?.id,
      },
    }),
    enabled: Boolean(selectedSemester),
  });
  const refreshRoster = () =>
    invalidate(
      "getAdminRoster",
      "listAdminClasses",
      "listStudents",
      "getGrid",
      "listClassCatalog",
      "getStudentHistory",
      "getArchiveGrid",
    );
  const refreshColumns = () => invalidate("listColumns", "getGrid", "listClassCatalog");
  const refreshClasses = () =>
    invalidate(
      "listAdminClasses",
      "listClassCatalog",
      "listAssignmentMatrix",
      "getAssignments",
      "getStudentHistory",
    );

  const [moveRequest, setMoveRequest] = useState<MoveRequest>();
  const move = useMutation({
    ...moveAdminRosterMutation(),
    onMutate: () => toast.loading(t("classWorkspace.movingStudent"), { id: "move-student" }),
    onSuccess: () => void refreshRoster(),
    onSettled: () => {
      toast.dismiss("move-student");
      setMoveRequest(undefined);
    },
  });
  function performMove(request: MoveRequest) {
    move.mutate(
      {
        body: {
          student_ids: request.studentIds,
          target_class_id: request.targetClassId,
          allow_grade_change: false,
        },
      },
      {
        onSuccess: (result) => {
          const target = request.targetClass;
          notifyDone(
            result.changed === 0
              ? t("classWorkspace.studentsAlreadyThere", { target })
              : request.names.length === 1
                ? t("classWorkspace.studentMoved", { name: request.names[0], target })
                : t("classWorkspace.studentsMoved", { count: result.changed, target }),
            result.action_id,
          );
        },
      },
    );
  }
  /** Every move is confirmed first, unless the admin opted out for this browser session. */
  function requestMove(studentIds: number[], targetClassId: number) {
    const target = gradeClasses.find((item) => item.id === targetClassId);
    if (!selectedClass || !target || move.isPending || studentIds.length === 0) return;
    const request: MoveRequest = {
      studentIds,
      names: roster
        .filter((student) => studentIds.includes(student.student_id))
        .map((student) => student.full_name),
      fromClasses: [selectedClass.name],
      targetClassId,
      targetClass: target.name,
    };
    if (moveConfirmationSkipped()) performMove(request);
    else setMoveRequest(request);
  }
  const [addingClass, setAddingClass] = useState(false);
  const [newSection, setNewSection] = useState("");
  const createClass = useMutation({
    ...createAdminClassMutation(),
    onSuccess: (created) => {
      updateSearch({ class: created.id });
      setNewSection("");
      setAddingClass(false);
      notifyDone(t("classes.added", { className: created.name }), created.action_id);
      void refreshClasses();
    },
  });
  const yearWritable = selectedYear?.status !== "archived";
  const columnsWritable =
    selectedYear?.status === "setup" ||
    (selectedYear?.status === "active" && selectedSemester?.status === "open");

  const prefetchRoster = useCallback(
    (classId: number) =>
      queryClient.prefetchQuery({
        ...getAdminRosterOptions({ path: { class_id: classId } }),
        staleTime: 30_000,
      }),
    [queryClient],
  );
  usePrefetchSiblings(gradeClasses, prefetchRoster);

  if (yearsError || classesError || rosterError || columnsError) {
    return <EmptyState title={t("errors.load")} />;
  }
  if (yearsPending || (selectedYear && classesPending)) return <PageSkeleton />;

  function dropOnClass(event: DragEvent, targetClassId: number) {
    event.preventDefault();
    const transferredStudentId = Number(
      event.dataTransfer.getData("application/x-flrc-student-id"),
    );
    const studentId = transferredStudentId || draggedStudentId;
    if (!studentId || targetClassId === selectedClass?.id) return;
    requestMove([studentId], targetClassId);
    setDraggedStudentId(undefined);
  }

  return (
    <AdminPage title={t("classWorkspace.title")} description={t("classWorkspace.description")}>
      {selectedYear ? (
        <AcademicContextBar
          years={years}
          yearId={selectedYear.id}
          semesterNumber={selectedSemester?.number ?? 1}
          onYearChange={(next) => {
            updateSearch({ year: next, class: undefined });
            // The new year shows its open semester (else its first).
            setSemesterNumber(undefined);
          }}
          onSemesterChange={setSemesterNumber}
          labels={academicContextLabels(t, t("classWorkspace.readOnly"))}
        />
      ) : null}

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 shadow-card xl:flex-row xl:items-center">
        <Segmented
          ariaLabel={t("classes.gradeLevel")}
          options={GRADES.map((item) => ({ value: item, label: gradeTabLabel(t, item) }))}
          value={grade}
          onChange={(next) => updateSearch({ grade: next, class: undefined })}
          className="max-w-full"
        />
        <Segmented
          ariaLabel={t("classWorkspace.subject")}
          options={SUBJECTS.map((item) => ({ value: item, label: t(`subjects.${item}`) }))}
          value={subject}
          onChange={(next) => {
            updateSearch({ subject: next });
            setColumnOwner(next === "english" ? "main" : next);
          }}
          className="max-w-full"
        />
        <span className="ml-auto text-xs text-muted-foreground">
          {t("classWorkspace.sortHint")}
        </span>
      </div>

      <div className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(5rem,1fr))] items-end gap-1 border-b border-border px-1 pt-1">
        {gradeClasses.map((schoolClass) => {
          const active = schoolClass.id === selectedClass?.id;
          const dropTarget = draggedStudentId && !active;
          return (
            <button
              key={schoolClass.id}
              type="button"
              aria-current={active ? "page" : undefined}
              className={[
                "relative min-w-0 rounded-t-xl border border-b-0 px-2 py-2 text-left text-xs outline-none transition-colors sm:text-sm",
                active
                  ? "border-border bg-card font-semibold text-foreground"
                  : "border-transparent bg-muted/45 text-muted-foreground hover:bg-muted",
                dropTarget
                  ? "hover:border-primary hover:bg-accent hover:text-accent-foreground"
                  : "",
              ].join(" ")}
              onPointerEnter={() => void prefetchRoster(schoolClass.id)}
              onFocus={() => void prefetchRoster(schoolClass.id)}
              onClick={() => updateSearch({ class: schoolClass.id })}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => dropOnClass(event, schoolClass.id)}
            >
              <span className="block">{schoolClass.name}</span>
              <span className="block text-[0.6875rem] font-normal text-muted-foreground">
                {t("classWorkspace.studentCount", { count: schoolClass.student_count })}
              </span>
            </button>
          );
        })}
        {yearWritable ? (
          addingClass ? (
            <form
              className="mb-1 flex items-center gap-1 rounded-lg bg-muted p-1"
              onSubmit={(event) => {
                event.preventDefault();
                if (!selectedYear || !newSection.trim()) return;
                createClass.mutate({
                  body: {
                    year_id: selectedYear.id,
                    grade_level: grade,
                    section: newSection.trim(),
                  },
                });
              }}
            >
              <Input
                autoFocus
                aria-label={t("classes.section")}
                className="w-20"
                value={newSection}
                onChange={(event) => setNewSection(event.target.value)}
                placeholder={t("classes.section")}
              />
              <Button
                type="submit"
                size="icon-sm"
                aria-label={t("classes.add")}
                pending={createClass.isPending}
                pendingLabel={t("feedback.saving")}
              >
                <PlusIcon />
              </Button>
            </form>
          ) : (
            <Button
              className="mb-1 shrink-0"
              variant="ghost"
              size="sm"
              onClick={() => setAddingClass(true)}
            >
              <PlusIcon />
              {t("classes.add")}
            </Button>
          )
        ) : null}
      </div>

      {!selectedClass ? (
        <EmptyState
          title={t("classWorkspace.noClassTitle")}
          description={t("classWorkspace.noClassDescription")}
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Segmented
              ariaLabel={t("classWorkspace.mode")}
              options={[
                { value: "table", label: t("classWorkspace.tableTab") },
                { value: "remove", label: t("classWorkspace.remove") },
              ]}
              value={mode}
              onChange={setMode}
            />
            {yearWritable ? (
              <ClassActions
                schoolClass={selectedClass}
                yearStatus={selectedYear!.status}
                onEdited={(updated) => {
                  updateSearch({ grade: updated.grade_level, class: updated.id });
                  return refreshClasses();
                }}
                onDeleted={() => {
                  updateSearch({ class: undefined });
                  return refreshClasses();
                }}
              />
            ) : null}
          </div>
          {mode === "remove" ? (
            <ClassRemovePanel
              key={`${selectedClass.id}-${selectedSemester?.id}-${subject}`}
              classId={selectedClass.id}
              className={selectedClass.name}
              semesterId={selectedSemester?.id}
              grade={grade}
              subject={subject}
              roster={roster}
              columns={columns}
              yearWritable={yearWritable}
              columnsWritable={columnsWritable}
              onRosterChanged={refreshRoster}
              onColumnsChanged={refreshColumns}
            />
          ) : null}
          <Card hidden={mode === "remove"}>
            <CardBody className="space-y-3 p-3">
              <ClassTeachers
                yearId={selectedYear!.id}
                classId={selectedClass.id}
                className={selectedClass.name}
                grade={grade}
                writable={yearWritable}
              />
              <ClassAddColumn
                grade={grade}
                subject={subject}
                semesterId={selectedSemester?.id}
                columns={columns}
                writable={columnsWritable}
                columnOwner={columnOwner}
                setColumnOwner={setColumnOwner}
                onChanged={refreshColumns}
              />
            </CardBody>
          </Card>
          <ClassRosterTable
            yearId={selectedYear!.id}
            classId={selectedClass.id}
            className={selectedClass.name}
            grade={grade}
            subject={subject}
            semesterId={selectedSemester?.id}
            roster={roster}
            rosterPending={rosterPending}
            columns={columns}
            moveTargets={gradeClasses.filter((item) => item.id !== selectedClass.id)}
            yearWritable={yearWritable}
            columnsWritable={columnsWritable}
            setDraggedStudentId={setDraggedStudentId}
            onMoveRequest={requestMove}
            onRosterChanged={refreshRoster}
            onColumnsChanged={refreshColumns}
            hidden={mode === "remove"}
          />
          {mode === "table" ? (
            <>
              <p className="text-xs text-muted-foreground">{t("classWorkspace.dragHint")}</p>
              <p className="text-xs text-muted-foreground">{t("classWorkspace.dragColumnsHint")}</p>
            </>
          ) : null}
        </>
      )}
      <MoveStudentsDialog
        request={moveRequest}
        pending={move.isPending}
        onCancel={() => setMoveRequest(undefined)}
        onConfirm={performMove}
      />
    </AdminPage>
  );
}
