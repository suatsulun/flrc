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
import { createFileRoute } from "@tanstack/react-router";
import { PlusIcon } from "lucide-react";
import { useCallback, useMemo, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AdminPage } from "../../admin/AdminPage";
import { ClassAddColumn } from "../../admin/ClassAddColumn";
import { ClassRemovePanel } from "../../admin/ClassRemovePanel";
import { ClassRosterTable } from "../../admin/ClassRosterTable";
import { ClassTeachers } from "../../admin/ClassTeachers";
import { useRefreshQueries } from "../../admin/use-refresh-queries";

const SUBJECTS = ["english", "german", "french"] as const;
type Subject = (typeof SUBJECTS)[number];
type Role = ColumnCreate["owner_role"];

export const Route = createFileRoute("/_auth/classes")({ component: ClassesPage });

function ClassesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const invalidate = useRefreshQueries();
  const [columnOwner, setColumnOwner] = useState<Role>("main");
  const {
    data: years = [],
    isPending: yearsPending,
    isError: yearsError,
  } = useQuery(listYearsOptions());
  const [yearId, setYearId] = useState<number>();
  const selectedYear =
    years.find((item) => item.id === yearId) ??
    years.find((item) => item.status === "active") ??
    years[0];
  const [semesterNumber, setSemesterNumber] = useState(1);
  const selectedSemester =
    selectedYear?.semesters.find((item) => item.number === semesterNumber) ??
    selectedYear?.semesters.find((item) => item.status === "open") ??
    selectedYear?.semesters[0];

  const [grade, setGrade] = useState<number>(5);
  const [subject, setSubject] = useState<Subject>("english");
  const [classId, setClassId] = useState<number>();
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

  const move = useMutation({
    ...moveAdminRosterMutation(),
    onMutate: () => toast.loading(t("classWorkspace.movingStudent"), { id: "move-student" }),
    onSuccess: () => {
      toast.success(t("classWorkspace.studentMoved"), { id: "move-student" });
      void refreshRoster();
    },
    onError: () => toast.dismiss("move-student"),
  });
  const [addingClass, setAddingClass] = useState(false);
  const [newSection, setNewSection] = useState("");
  const createClass = useMutation({
    ...createAdminClassMutation(),
    onSuccess: (created) => {
      setClassId(created.id);
      setNewSection("");
      setAddingClass(false);
      toast.success(t("classWorkspace.classAdded"));
      void invalidate("listAdminClasses", "listClassCatalog");
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
    move.mutate({
      body: {
        student_ids: [studentId],
        target_class_id: targetClassId,
        allow_grade_change: false,
      },
    });
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
            setYearId(next);
            setClassId(undefined);
            const nextYear = years.find((item) => item.id === next);
            setSemesterNumber(
              nextYear?.semesters.find((item) => item.status === "open")?.number ??
                nextYear?.semesters[0]?.number ??
                1,
            );
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
          onChange={(next) => {
            setGrade(next);
            setClassId(undefined);
          }}
          className="max-w-full"
        />
        <Segmented
          ariaLabel={t("classWorkspace.subject")}
          options={SUBJECTS.map((item) => ({ value: item, label: t(`subjects.${item}`) }))}
          value={subject}
          onChange={(next) => {
            setSubject(next);
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
              onClick={() => setClassId(schoolClass.id)}
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
          <Segmented
            ariaLabel={t("classWorkspace.mode")}
            options={[
              { value: "table", label: t("classWorkspace.tableTab") },
              { value: "remove", label: t("classWorkspace.remove") },
            ]}
            value={mode}
            onChange={setMode}
          />
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
            classId={selectedClass.id}
            grade={grade}
            subject={subject}
            semesterId={selectedSemester?.id}
            roster={roster}
            rosterPending={rosterPending}
            columns={columns}
            yearWritable={yearWritable}
            columnsWritable={columnsWritable}
            setDraggedStudentId={setDraggedStudentId}
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
    </AdminPage>
  );
}
