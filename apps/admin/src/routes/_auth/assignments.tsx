import { GRADES, academicContextLabels, gradeLabel, gradeTabLabel } from "@flrc/i18n";
import { useState, type DragEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import {
  ChevronDownIcon,
  ChevronUpIcon,
  GripVerticalIcon,
  LanguagesIcon,
  PlusIcon,
  UserRoundIcon,
  XIcon,
} from "lucide-react";
import { toast } from "sonner";
import {
  listAdminClassesOptions,
  listAssignmentMatrixOptions,
  listManagedUsersOptions,
  listYearsOptions,
  replaceAssignmentMatrixMutation,
  type AdminClassOut,
  type ManagedUserOut,
  type MatrixSlotOut,
} from "@flrc/api-client";
import { AcademicContextBar } from "@flrc/ui/components/academic-context-bar";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody } from "@flrc/ui/components/card";
import { Checkbox } from "@flrc/ui/components/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Segmented } from "@flrc/ui/components/segmented";
import { useIsPhone } from "@flrc/ui/hooks/use-is-phone";
import { cn } from "@flrc/ui/lib/utils";
import { useRefreshQueries } from "../../admin/use-refresh-queries";
import { useReturnFocus } from "../../admin/use-return-focus";
import { AdminPage } from "../../admin/AdminPage";
import { useNotifyDone } from "../../admin/undo-toast";
import { AssignmentsBoardSkeleton, AssignmentsSkeleton } from "../../admin/page-skeletons";

type Role = "main" | "skills" | "german" | "french";
type TeacherFilter = "all" | "primary" | "middle" | "german" | "french";
type PickerTarget = { teacherId: number; role: Role; grade: number };

export const Route = createFileRoute("/_auth/assignments")({ component: AssignmentsPage });

function rolesFor(field: string): Role[] {
  if (field === "german") return ["german"];
  if (field === "french") return ["french"];
  return ["main", "skills"];
}

/**
 * Grades a teacher may hold a class role in: the server's stage rule for English (primary up to
 * grade 4, middle from 5), and second languages from grade 4, where they start.
 */
function eligibleGrades(teacher: ManagedUserOut): number[] {
  return GRADES.filter((item) => {
    if (teacher.teaching_field === "english") {
      return teacher.teaching_stage === "primary" ? item <= 4 : item >= 5;
    }
    return item >= 4;
  });
}

function AssignmentsPage() {
  const { t } = useTranslation();
  const refresh = useRefreshQueries();
  const notifyDone = useNotifyDone();
  const isPhone = useIsPhone();
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
  // Phones show one line per teacher until it is tapped open; desktops show every card open.
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<number>>(new Set());
  // The target outlives `pickerOpen` so the dialog keeps its content while it animates closed.
  const [picker, setPicker] = useState<PickerTarget>();
  const [pickerOpen, setPickerOpen] = useState(false);
  const pickerFocus = useReturnFocus();

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
    onSuccess: () =>
      refresh("listAssignmentMatrix", "getAssignments", "getGrid", "listClassCatalog"),
    onSettled: () => toast.dismiss("assignment-save"),
  });

  /** Assign or unassign one class slot; each save gets its own toast with Undo. */
  async function change(
    classId: number,
    role: Role,
    teacher: { id: number; full_name: string },
    assign: boolean,
  ) {
    if (!selectedYear || !writable) return;
    const message = t(assign ? "assignmentBoard.assigned" : "assignmentBoard.unassigned", {
      teacher: teacher.full_name,
      className: classes.find((item) => item.id === classId)?.name ?? classId,
      role: t(`roles.${role}`),
    });
    // A failed save is reported by the global error toast.
    const saved = await save
      .mutateAsync({
        path: { year_id: selectedYear.id },
        body: { changes: [{ class_id: classId, role, user_id: assign ? teacher.id : null }] },
      })
      .catch(() => undefined);
    if (saved) notifyDone(message, saved.action_id);
  }

  function drop(event: DragEvent, role: Role, teacher: { id: number; full_name: string }) {
    event.preventDefault();
    if (draggedClassId) void change(draggedClassId, role, teacher, true);
    setDraggedClassId(undefined);
  }

  function changeTeacherFilter(value: TeacherFilter) {
    setTeacherFilter(value);
    if (value === "primary" && grade > 4) setGrade(1);
    if (value === "middle" && grade < 5) setGrade(5);
    if ((value === "german" || value === "french") && grade < 4) setGrade(4);
  }

  function toggleTeacher(teacherId: number) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (!next.delete(teacherId)) next.add(teacherId);
      return next;
    });
  }

  function openPicker(opener: HTMLElement, teacher: ManagedUserOut, role: Role) {
    pickerFocus.remember(opener);
    const grades = eligibleGrades(teacher);
    setPicker({
      teacherId: teacher.id,
      role,
      grade: grades.includes(grade) ? grade : (grades[0] ?? grade),
    });
    setPickerOpen(true);
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
  const pickerTeacher = users.find((item) => item.id === picker?.teacherId);
  const description = t(
    isPhone ? "assignmentBoard.phoneDescription" : "assignmentBoard.description",
  );

  if (yearsPending || usersPending) return <AssignmentsSkeleton />;

  const contextBar = selectedYear ? (
    <AcademicContextBar
      years={years}
      yearId={selectedYear.id}
      semesterNumber={semester}
      onYearChange={setYearId}
      onSemesterChange={setSemester}
      labels={academicContextLabels(t, t("classWorkspace.readOnly"))}
    />
  ) : null;
  // A year switch keeps the year bar on screen while the new year's board loads.
  if (selectedYear && (classesPending || matrixPending)) {
    return (
      <AdminPage title={t("assignmentBoard.title")} description={description}>
        {contextBar}
        <AssignmentsBoardSkeleton />
      </AdminPage>
    );
  }

  return (
    <AdminPage title={t("assignmentBoard.title")} description={description}>
      {contextBar}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-2 md:space-y-4">
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
            visibleTeachers.map((teacher) => {
              const expanded = !isPhone || expandedIds.has(teacher.id);
              const rolesId = `teacher-roles-${teacher.id}`;
              const badges = (
                <>
                  <Badge tone="outline">{t(`subjects.${teacher.teaching_field}`)}</Badge>
                  {teacher.teaching_stage ? (
                    <Badge tone="neutral">{t(`teachingStages.${teacher.teaching_stage}`)}</Badge>
                  ) : null}
                </>
              );
              return (
                <Card
                  key={teacher.id}
                  data-testid="assignment-teacher-card"
                  data-teaching-field={teacher.teaching_field}
                  data-teaching-stage={teacher.teaching_stage ?? undefined}
                >
                  <CardBody
                    className={cn("space-y-3 p-3", isPhone && (expanded ? "pt-0.5" : "py-0.5"))}
                  >
                    {isPhone ? (
                      <h2>
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-controls={expanded ? rolesId : undefined}
                          className="flex min-h-11 w-full items-center gap-2.5 rounded-lg text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                          onClick={() => toggleTeacher(teacher.id)}
                        >
                          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
                            <UserRoundIcon className="size-4" />
                          </span>
                          {/* Badges sit under the name so a long name keeps the row's width. */}
                          <span className="min-w-0 flex-1">
                            <span
                              className={cn(
                                "block text-sm font-semibold",
                                expanded ? "break-words" : "truncate",
                              )}
                            >
                              {teacher.full_name}
                            </span>
                            {expanded ? (
                              <span className="block truncate text-xs text-muted-foreground">
                                {teacher.email}
                              </span>
                            ) : null}
                            <span className="mt-0.5 flex flex-wrap gap-1">
                              {badges}
                              <AssignedCountBadge teacherId={teacher.id} matrix={matrix} />
                            </span>
                          </span>
                          {expanded ? (
                            <ChevronUpIcon className="size-4 shrink-0 text-muted-foreground" />
                          ) : (
                            <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
                          )}
                        </button>
                      </h2>
                    ) : (
                      <header className="flex items-center gap-3">
                        <span className="grid size-9 place-items-center rounded-full bg-accent text-accent-foreground">
                          <UserRoundIcon className="size-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <h2 className="truncate text-sm font-semibold">{teacher.full_name}</h2>
                          <p className="truncate text-xs text-muted-foreground">{teacher.email}</p>
                        </div>
                        <div className="flex flex-wrap justify-end gap-1">{badges}</div>
                      </header>
                    )}

                    {expanded ? (
                      <div
                        id={rolesId}
                        className={`grid gap-2 ${rolesFor(teacher.teaching_field).length > 1 ? "sm:grid-cols-2" : ""}`}
                      >
                        {rolesFor(teacher.teaching_field).map((role) => {
                          const assigned = matrix.filter(
                            (item) => item.user_id === teacher.id && item.role === role,
                          );
                          return (
                            <section
                              key={role}
                              className={cn(
                                "min-h-24 rounded-lg border border-dashed border-border-strong bg-muted/30 p-2 transition-colors hover:border-primary hover:bg-accent/45",
                                isPhone && "min-h-0",
                              )}
                              onDragOver={(event) => event.preventDefault()}
                              onDrop={(event) => drop(event, role, teacher)}
                            >
                              {isPhone ? (
                                <div className="mb-2 flex items-center justify-between gap-2">
                                  <span className="flex min-w-0 items-center gap-2 text-xs font-semibold text-muted-foreground">
                                    <LanguagesIcon className="size-3.5 shrink-0" />
                                    {t(`roles.${role}`)}
                                    <Badge tone="neutral">{assigned.length}</Badge>
                                  </span>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={!writable || save.isPending}
                                    aria-label={`${teacher.full_name} — ${t(`roles.${role}`)} — ${t("assignmentBoard.addClass")}`}
                                    onClick={(event) =>
                                      openPicker(event.currentTarget, teacher, role)
                                    }
                                  >
                                    <PlusIcon />
                                    {t("assignmentBoard.addClass")}
                                  </Button>
                                </div>
                              ) : (
                                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                                  <LanguagesIcon className="size-3.5" />
                                  {t(`roles.${role}`)}
                                </div>
                              )}
                              <div className="flex flex-wrap gap-1.5">
                                {assigned.length === 0 ? (
                                  <span className="text-xs text-muted-foreground">
                                    {t(
                                      isPhone
                                        ? "assignmentBoard.noClassesAssigned"
                                        : "assignmentBoard.dropHere",
                                    )}
                                  </span>
                                ) : (
                                  assigned.map((slot) => {
                                    const schoolClass = classes.find(
                                      (item) => item.id === slot.class_id,
                                    );
                                    return (
                                      <span
                                        key={slot.class_id}
                                        className="inline-flex items-center gap-1 rounded-md border border-border bg-card py-1 pr-1 pl-2 text-xs font-medium shadow-card max-md:min-h-10 max-md:pl-2.5"
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
                                          onClick={() =>
                                            void change(slot.class_id, role, teacher, false)
                                          }
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
                    ) : null}
                  </CardBody>
                </Card>
              );
            })
          )}
        </div>

        <aside className="sticky top-18 hidden space-y-3 rounded-xl border border-border bg-card p-3 shadow-card md:block">
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

      {picker && pickerTeacher ? (
        <AssignmentClassPickerDialog
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          finalFocus={pickerFocus.finalFocus}
          teacher={pickerTeacher}
          role={picker.role}
          grade={picker.grade}
          onGradeChange={(next) => setPicker({ ...picker, grade: next })}
          classes={classes}
          matrix={matrix}
          disabled={!writable || save.isPending}
          onToggle={(classId, assign) => void change(classId, picker.role, pickerTeacher, assign)}
        />
      ) : null}
    </AdminPage>
  );
}

/** How many distinct classes a teacher holds any role in, shown on the collapsed phone row. */
function AssignedCountBadge({ teacherId, matrix }: { teacherId: number; matrix: MatrixSlotOut[] }) {
  const { t } = useTranslation();
  const count = new Set(
    matrix.filter((item) => item.user_id === teacherId).map((item) => item.class_id),
  ).size;
  return (
    <Badge tone={count > 0 ? "info" : "neutral"}>
      {t("assignmentBoard.classCount", { count })}
    </Badge>
  );
}

/**
 * The phone stand-in for dragging classes onto a role: tick the classes of one eligible grade.
 * Each tick is the same single-slot save a desktop drop makes, so a class held by another
 * teacher moves to this one, with the same toast and Undo.
 */
function AssignmentClassPickerDialog({
  open,
  onOpenChange,
  finalFocus,
  teacher,
  role,
  grade,
  onGradeChange,
  classes,
  matrix,
  disabled,
  onToggle,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  finalFocus: () => HTMLElement | boolean;
  teacher: ManagedUserOut;
  role: Role;
  grade: number;
  onGradeChange: (grade: number) => void;
  classes: AdminClassOut[];
  matrix: MatrixSlotOut[];
  disabled: boolean;
  onToggle: (classId: number, assign: boolean) => void;
}) {
  const { t } = useTranslation();
  const gradeClasses = classes.filter((item) => item.grade_level === grade);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        finalFocus={finalFocus}
        className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_auto_minmax(0,1fr)_auto] overflow-hidden"
      >
        <DialogHeader>
          <DialogTitle className="pr-8">
            {teacher.full_name} · {t(`roles.${role}`)}
          </DialogTitle>
          <DialogDescription>{t("assignmentBoard.pickerDescription")}</DialogDescription>
        </DialogHeader>
        <Segmented
          ariaLabel={t("classes.gradeLevel")}
          options={eligibleGrades(teacher).map((item) => ({
            value: item,
            label: gradeTabLabel(t, item),
          }))}
          value={grade}
          onChange={onGradeChange}
          className="justify-self-start"
        />
        {gradeClasses.length === 0 ? (
          <p className="rounded-xl border border-border px-4 py-6 text-center text-sm text-muted-foreground">
            {t("classWorkspace.noClassTitle")}
          </p>
        ) : (
          <ul
            aria-label={gradeLabel(t, grade)}
            className="max-h-[45dvh] min-h-0 divide-y divide-border overflow-y-auto rounded-xl border border-border"
          >
            {gradeClasses.map((schoolClass) => {
              const slot = matrix.find(
                (item) => item.class_id === schoolClass.id && item.role === role,
              );
              const mine = slot?.user_id === teacher.id;
              return (
                <li key={schoolClass.id}>
                  <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3 px-3.5 py-2.5 text-sm hover:bg-muted/60">
                    <span className="flex min-w-0 items-center gap-3">
                      <Checkbox
                        checked={mine}
                        disabled={disabled}
                        aria-label={schoolClass.name}
                        onCheckedChange={(checked) => onToggle(schoolClass.id, checked)}
                      />
                      <span className="min-w-0">
                        <span className="font-semibold">{schoolClass.name}</span>{" "}
                        <span className="text-xs text-muted-foreground">
                          {t("classWorkspace.studentCount", { count: schoolClass.student_count })}
                        </span>
                      </span>
                    </span>
                    {mine ? (
                      <Badge tone="success">{t("assignmentBoard.assignedLabel")}</Badge>
                    ) : slot ? (
                      <span className="max-w-36 truncate text-xs text-muted-foreground">
                        {slot.user_name}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {t("assignments.unassigned")}
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        <DialogFooter>
          <Button className="w-full" onClick={() => onOpenChange(false)}>
            {t("grid.commentEditorDone")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
