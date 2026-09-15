import { GRADES, academicContextLabels, gradeTabLabel } from "@flrc/i18n";
import { useState, type DragEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { GripVerticalIcon, LanguagesIcon, UserRoundIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import {
  listAdminClassesOptions,
  listAssignmentMatrixOptions,
  listManagedUsersOptions,
  listYearsOptions,
  replaceAssignmentMatrixMutation,
} from "@flrc/api-client";
import { AcademicContextBar } from "@flrc/ui/components/academic-context-bar";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { Segmented } from "@flrc/ui/components/segmented";
import { useRefreshQueries } from "../../admin/use-refresh-queries";
import { AdminPage } from "../../admin/AdminPage";

type Role = "main" | "skills" | "german" | "french";
type TeacherFilter = "all" | "primary" | "middle" | "german" | "french";

export const Route = createFileRoute("/_auth/assignments")({ component: AssignmentsPage });

function rolesFor(field: string): Role[] {
  if (field === "german") return ["german"];
  if (field === "french") return ["french"];
  return ["main", "skills"];
}

function AssignmentsPage() {
  const { t } = useTranslation();
  const refresh = useRefreshQueries();
  const { data: years = [], isPending: yearsPending } = useQuery(listYearsOptions());
  const [yearId, setYearId] = useState<number>();
  const selectedYear =
    years.find((item) => item.id === yearId) ??
    years.find((item) => item.status === "active") ??
    years[0];
  const [semester, setSemester] = useState(1);
  const [grade, setGrade] = useState<number>(5);
  const [teacherFilter, setTeacherFilter] = useState<TeacherFilter>("all");
  const [draggedClassId, setDraggedClassId] = useState<number>();

  const { data: classes = [], isPending: classesPending } = useQuery({
    ...listAdminClassesOptions({ path: { year_id: selectedYear?.id ?? 0 } }),
    enabled: Boolean(selectedYear),
  });
  const { data: matrix = [], isPending: matrixPending } = useQuery({
    ...listAssignmentMatrixOptions({ path: { year_id: selectedYear?.id ?? 0 } }),
    enabled: Boolean(selectedYear),
  });
  const { data: users = [], isPending: usersPending } = useQuery(
    listManagedUsersOptions({ query: { active: true } }),
  );
  const writable = selectedYear?.status !== "archived";

  const save = useMutation({
    ...replaceAssignmentMatrixMutation(),
    onMutate: () => toast.loading(t("assignmentBoard.saving"), { id: "assignment-save" }),
    onSuccess: () => {
      toast.success(t("assignmentBoard.saved"), { id: "assignment-save" });
      return refresh("listAssignmentMatrix", "getAssignments", "getGrid", "listClassCatalog");
    },
    onError: () => toast.dismiss("assignment-save"),
  });

  function change(classId: number, role: Role, userId: number | null) {
    if (!selectedYear || !writable) return;
    save.mutate({
      path: { year_id: selectedYear.id },
      body: { changes: [{ class_id: classId, role, user_id: userId }] },
    });
  }

  function drop(event: DragEvent, role: Role, userId: number) {
    event.preventDefault();
    if (draggedClassId) change(draggedClassId, role, userId);
    setDraggedClassId(undefined);
  }

  function changeTeacherFilter(value: TeacherFilter) {
    setTeacherFilter(value);
    if (value === "primary" && grade > 4) setGrade(1);
    if (value === "middle" && grade < 5) setGrade(5);
    if ((value === "german" || value === "french") && grade < 4) setGrade(4);
  }

  const visibleClasses = classes.filter((item) => item.grade_level === grade);
  const gradeOptions = GRADES.filter((item) => {
    if (teacherFilter === "primary") return item <= 4;
    if (teacherFilter === "middle") return item >= 5;
    if (teacherFilter === "german" || teacherFilter === "french") return item >= 4;
    return true;
  });
  const visibleTeachers = users.filter((teacher) => {
    if (teacherFilter === "all") return true;
    if (teacherFilter === "german" || teacherFilter === "french") {
      return teacher.teaching_field === teacherFilter;
    }
    return teacher.teaching_field === "english" && teacher.teaching_stage === teacherFilter;
  });

  if (yearsPending || usersPending || (selectedYear && (classesPending || matrixPending))) {
    return <PageSkeleton />;
  }

  return (
    <AdminPage title={t("assignmentBoard.title")} description={t("assignmentBoard.description")}>
      {selectedYear ? (
        <AcademicContextBar
          years={years}
          yearId={selectedYear.id}
          semesterNumber={semester}
          onYearChange={setYearId}
          onSemesterChange={setSemester}
          labels={academicContextLabels(t, t("classWorkspace.readOnly"))}
        />
      ) : null}

      {save.isError ? (
        <p
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive-surface px-4 py-3 text-sm text-destructive"
        >
          {t("assignmentBoard.saveFailed")}
        </p>
      ) : null}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2 shadow-card">
            <span className="text-xs font-semibold text-muted-foreground">
              {t("assignmentBoard.teacherFilter")}
            </span>
            <Segmented
              ariaLabel={t("assignmentBoard.teacherFilter")}
              value={teacherFilter}
              onChange={changeTeacherFilter}
              options={(["all", "primary", "middle", "german", "french"] as const).map((value) => ({
                value,
                label: t(`assignmentBoard.filters.${value}`),
              }))}
              size="sm"
            />
          </div>

          {visibleTeachers.length === 0 ? (
            <EmptyState title={t("assignmentBoard.filterEmpty")} />
          ) : (
            visibleTeachers.map((teacher) => (
              <Card
                key={teacher.id}
                data-testid="assignment-teacher-card"
                data-teaching-field={teacher.teaching_field}
                data-teaching-stage={teacher.teaching_stage ?? undefined}
              >
                <CardBody className="space-y-3 p-3">
                  <header className="flex items-center gap-3">
                    <span className="grid size-9 place-items-center rounded-full bg-accent text-accent-foreground">
                      <UserRoundIcon className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate text-sm font-semibold">{teacher.full_name}</h2>
                      <p className="truncate text-xs text-muted-foreground">{teacher.email}</p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-1">
                      <Badge tone="outline">{t(`subjects.${teacher.teaching_field}`)}</Badge>
                      {teacher.teaching_stage ? (
                        <Badge tone="neutral">
                          {t(`teachingStages.${teacher.teaching_stage}`)}
                        </Badge>
                      ) : null}
                    </div>
                  </header>

                  <div
                    className={`grid gap-2 ${rolesFor(teacher.teaching_field).length > 1 ? "sm:grid-cols-2" : ""}`}
                  >
                    {rolesFor(teacher.teaching_field).map((role) => {
                      const assigned = matrix.filter(
                        (item) => item.user_id === teacher.id && item.role === role,
                      );
                      return (
                        <section
                          key={role}
                          className="min-h-24 rounded-lg border border-dashed border-border-strong bg-muted/30 p-2 transition-colors hover:border-primary hover:bg-accent/45"
                          onDragOver={(event) => event.preventDefault()}
                          onDrop={(event) => drop(event, role, teacher.id)}
                        >
                          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                            <LanguagesIcon className="size-3.5" />
                            {t(`roles.${role}`)}
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {assigned.length === 0 ? (
                              <span className="text-xs text-muted-foreground">
                                {t("assignmentBoard.dropHere")}
                              </span>
                            ) : (
                              assigned.map((slot) => {
                                const schoolClass = classes.find(
                                  (item) => item.id === slot.class_id,
                                );
                                return (
                                  <span
                                    key={slot.class_id}
                                    className="inline-flex items-center gap-1 rounded-md border border-border bg-card py-1 pr-1 pl-2 text-xs font-medium shadow-card"
                                  >
                                    {schoolClass?.name ?? slot.class_id}
                                    <Button
                                      variant="ghost"
                                      size="icon-sm"
                                      disabled={!writable || save.isPending}
                                      pending={
                                        save.isPending &&
                                        save.variables?.body.changes.some(
                                          (change) =>
                                            change.class_id === slot.class_id &&
                                            change.role === role,
                                        )
                                      }
                                      pendingLabel={t("assignmentBoard.saving")}
                                      aria-label={t("assignmentBoard.remove", {
                                        className: schoolClass?.name,
                                        teacher: teacher.full_name,
                                      })}
                                      onClick={() => change(slot.class_id, role, null)}
                                    >
                                      <XIcon />
                                    </Button>
                                  </span>
                                );
                              })
                            )}
                          </div>
                        </section>
                      );
                    })}
                  </div>
                </CardBody>
              </Card>
            ))
          )}
        </div>

        <aside className="sticky top-18 space-y-3 rounded-xl border border-border bg-card p-3 shadow-card">
          <div>
            <h2 className="text-sm font-semibold">{t("assignmentBoard.classTray")}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t("assignmentBoard.classTrayHint")}
            </p>
          </div>
          <Segmented
            ariaLabel={t("classes.gradeLevel")}
            options={gradeOptions.map((item) => ({ value: item, label: gradeTabLabel(t, item) }))}
            value={grade}
            onChange={setGrade}
            className="max-w-full"
          />
          <div className="grid grid-cols-2 gap-2">
            {visibleClasses.map((schoolClass) => (
              <button
                key={schoolClass.id}
                type="button"
                draggable={writable}
                disabled={!writable}
                className="flex cursor-grab items-center gap-2 rounded-lg border border-border bg-muted/35 px-2.5 py-2 text-left text-sm font-semibold outline-none transition-colors hover:border-primary hover:bg-accent active:cursor-grabbing disabled:cursor-not-allowed disabled:opacity-50"
                onDragStart={() => setDraggedClassId(schoolClass.id)}
                onDragEnd={() => setDraggedClassId(undefined)}
              >
                <GripVerticalIcon className="size-4 text-muted-foreground" />
                {schoolClass.name}
              </button>
            ))}
          </div>
        </aside>
      </div>
    </AdminPage>
  );
}
