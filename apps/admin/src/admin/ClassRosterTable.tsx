import { Card } from "@flrc/ui/components/card";
import { SkeletonStudentCards, SkeletonTableRows } from "@flrc/ui/components/skeleton";
import { StudentGradeCards, useGradeTableView } from "@flrc/ui/components/student-grade-cards";
import { TableCaption, TableScroll } from "@flrc/ui/components/table";
import type { ColumnCreate } from "@flrc/api-client";
import {
  addAdminRosterStudentMutation,
  patchAdminRosterStudentMutation,
  setStudentLanguageMutation,
  type AdminClassOut,
  type ColumnOut,
  type RosterStudentOut,
} from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Checkbox } from "@flrc/ui/components/checkbox";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { useMutation } from "@tanstack/react-query";
import { GripVerticalIcon, PlusIcon, UserRoundPlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ClassColumnHeaders } from "./ClassColumnHeaders";
import { RenameFieldDialog } from "./RenameFieldDialog";
import { useNotifyDone } from "./undo-toast";
import { useReturnFocus } from "./use-return-focus";
type Subject = ColumnCreate["subject"];
type Language = "german" | "french";
/**
 * Pinned identity columns, in rem (ADR-045): the selection (and drag) handle, the school
 * number and the name. Each sticky offset is the width of the columns before it, so the
 * `left-*` classes must stay in step with the widths; the trailing slack column keeps the
 * declared widths exact instead of stretching them. Phones pin narrower columns so the
 * language and sütunlar keep room to scroll.
 */
const ROSTER_PINNED = {
  desktop: { handle: 4, number: 7, name: 14, numberLeft: "left-16", nameLeft: "left-44" },
  phone: {
    handle: 2.5,
    number: 4.5,
    name: 7.5,
    numberLeft: "left-[2.5rem]",
    nameLeft: "left-[7rem]",
  },
} as const;

export function ClassRosterTable({
  yearId,
  classId,
  className,
  grade,
  subject,
  semesterId,
  roster,
  rosterPending,
  columns,
  moveTargets,
  yearWritable,
  columnsWritable,
  setDraggedStudentId,
  onMoveRequest,
  onRosterChanged,
  onColumnsChanged,
  hidden,
}: {
  yearId: number;
  classId: number;
  className: string;
  grade: number;
  subject: Subject;
  semesterId?: number;
  roster: RosterStudentOut[];
  rosterPending: boolean;
  columns: ColumnOut[];
  /** The other classes of this grade, where selected students can be moved. */
  moveTargets: AdminClassOut[];
  yearWritable: boolean;
  columnsWritable: boolean;
  hidden: boolean;
  setDraggedStudentId: (id: number | undefined) => void;
  onMoveRequest: (studentIds: number[], targetClassId: number, opener: EventTarget | null) => void;
  onRosterChanged: () => Promise<unknown>;
  onColumnsChanged: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const notifyDone = useNotifyDone();
  const { isPhone, effectiveView } = useGradeTableView();
  const pinned = isPhone ? ROSTER_PINNED.phone : ROSTER_PINNED.desktop;
  const visibleColumns = columns.filter((column) => column.is_active);
  const [studentNumber, setStudentNumber] = useState("");
  const [studentName, setStudentName] = useState("");
  const [studentLanguage, setStudentLanguage] = useState<Language | "">("");
  const [renaming, setRenaming] = useState<ColumnOut>();
  const renameFocus = useReturnFocus();
  // A typed school number shows until its save settles; then the stored value shows again,
  // so an Undo or a refused save is never hidden behind (or re-sent from) a stale draft.
  const [numberDrafts, setNumberDrafts] = useState<Record<number, string>>({});
  const dropNumberDraft = (studentId: number) =>
    setNumberDrafts((drafts) => {
      const next = { ...drafts };
      delete next[studentId];
      return next;
    });
  // Selection belongs to one class; students who left the roster drop out of it.
  const [selection, setSelection] = useState<{ classId: number; ids: number[] }>();
  const selectedIds =
    selection?.classId === classId
      ? selection.ids.filter((id) => roster.some((student) => student.student_id === id))
      : [];
  const allSelected = roster.length > 0 && selectedIds.length === roster.length;
  const [moveTarget, setMoveTarget] = useState("");
  const [bulkLanguage, setBulkLanguage] = useState<Language | "none" | "">("");
  const languageLabel = (language: string | null | undefined) =>
    language ? t(`subjects.${language}`) : "";

  const addStudent = useMutation({
    ...addAdminRosterStudentMutation(),
    // The toast names the class the student was added to, even after a tab switch.
    onMutate: () => ({ className }),
    onSuccess: (added, _variables, submitted) => {
      setStudentNumber("");
      setStudentName("");
      notifyDone(
        t("classWorkspace.studentAdded", {
          name: added.full_name,
          className: submitted.className,
        }),
        added.action_id,
      );
      void onRosterChanged();
    },
  });
  const patchStudent = useMutation({
    ...patchAdminRosterStudentMutation(),
    onSuccess: async (saved, { body }) => {
      const name = saved.full_name;
      const message =
        "language" in body
          ? saved.language
            ? t("roster.languageSaved", { name, language: languageLabel(saved.language) })
            : t("roster.languageCleared", { name })
          : saved.school_number != null
            ? t("roster.numberSaved", { name, number: saved.school_number })
            : t("roster.numberCleared", { name });
      notifyDone(message, saved.action_id);
      await onRosterChanged();
    },
    onSettled: (_saved, _error, { path }) => dropNumberDraft(path.student_id),
  });
  const setLanguages = useMutation({
    ...setStudentLanguageMutation(),
    onSuccess: (result, { body }) => {
      setBulkLanguage("");
      notifyDone(
        body.language
          ? t("roster.bulkLanguageSaved", {
              count: result.changed,
              language: languageLabel(body.language),
            })
          : t("roster.bulkLanguageCleared", { count: result.changed }),
        result.action_id,
      );
      void onRosterChanged();
    },
  });

  function addRosterStudent(event: FormEvent) {
    event.preventDefault();
    if (!studentNumber || !studentName.trim()) return;
    addStudent.mutate({
      path: { class_id: classId },
      body: {
        school_number: Number(studentNumber),
        full_name: studentName.trim(),
        language: grade >= 4 ? studentLanguage || null : null,
      },
    });
  }

  function toggleStudent(studentId: number, selected: boolean) {
    const ids = selectedIds.filter((id) => id !== studentId);
    setSelection({ classId, ids: selected ? [...ids, studentId] : ids });
  }

  // The controls a student row (or phone card) edits, the same in both layouts.
  const selectStudentCheckbox = (student: RosterStudentOut, className?: string) => (
    <Checkbox
      className={className}
      aria-label={t("roster.selectStudent", { name: student.full_name })}
      checked={selectedIds.includes(student.student_id)}
      onCheckedChange={(checked) => toggleStudent(student.student_id, checked === true)}
    />
  );
  const selectAllCheckbox = (className?: string) => (
    <Checkbox
      className={className}
      aria-label={t("roster.selectAll")}
      checked={allSelected}
      disabled={roster.length === 0}
      onCheckedChange={(checked) =>
        setSelection({
          classId,
          ids: checked === true ? roster.map((student) => student.student_id) : [],
        })
      }
    />
  );
  const schoolNumberInput = (student: RosterStudentOut, className: string) => (
    <Input
      className={className}
      inputMode="numeric"
      aria-label={`${student.full_name} — ${t("students.schoolNumber")}`}
      value={numberDrafts[student.student_id] ?? student.school_number ?? ""}
      disabled={!yearWritable || patchStudent.isPending}
      onChange={(event) => {
        const value = event.currentTarget.value;
        setNumberDrafts((drafts) => ({ ...drafts, [student.student_id]: value }));
      }}
      onBlur={() => {
        const draft = numberDrafts[student.student_id];
        if (draft === undefined) return;
        const next = draft.trim() ? Number(draft.trim()) : null;
        if (next === student.school_number) {
          dropNumberDraft(student.student_id);
          return;
        }
        patchStudent.mutate({
          path: {
            class_id: classId,
            student_id: student.student_id,
          },
          body: { school_number: next },
        });
      }}
    />
  );
  const languageSelect = (student: RosterStudentOut, className: string) => (
    <NativeSelect
      className={className}
      aria-label={`${student.full_name} — ${t("roster.language")}`}
      value={student.language ?? ""}
      disabled={!yearWritable || patchStudent.isPending}
      onChange={(event) =>
        patchStudent.mutate({
          path: {
            class_id: classId,
            student_id: student.student_id,
          },
          body: {
            language: (event.target.value || null) as Language | null,
          },
        })
      }
    >
      <option value="">{t("import.noLanguage")}</option>
      <option value="german" disabled={grade < 4}>
        {t("subjects.german")}
      </option>
      <option value="french" disabled={grade < 4}>
        {t("subjects.french")}
      </option>
    </NativeSelect>
  );
  const studentNumberField = (className: string) => (
    <Input
      className={className}
      type="number"
      min="1"
      required
      value={studentNumber}
      onChange={(event) => setStudentNumber(event.target.value)}
      placeholder={t("students.schoolNumber")}
      aria-label={t("students.schoolNumber")}
    />
  );
  const studentNameField = (className?: string) => (
    <Input
      className={className}
      required
      value={studentName}
      onChange={(event) => setStudentName(event.target.value)}
      placeholder={t("students.fullName")}
      aria-label={t("students.fullName")}
    />
  );
  const studentLanguageField = (className: string) =>
    grade >= 4 ? (
      <NativeSelect
        className={className}
        aria-label={t("roster.language")}
        value={studentLanguage}
        onChange={(event) => setStudentLanguage(event.target.value as Language | "")}
      >
        <option value="">{t("roster.language")}</option>
        <option value="german">{t("subjects.german")}</option>
        <option value="french">{t("subjects.french")}</option>
      </NativeSelect>
    ) : null;
  const addStudentButton = (className?: string) => (
    <Button
      type="submit"
      className={className}
      pending={addStudent.isPending}
      pendingLabel={t("feedback.saving")}
    >
      <PlusIcon />
      {t("classWorkspace.addStudent")}
    </Button>
  );

  const bulkToolbar =
    yearWritable && !hidden && selectedIds.length > 0 ? (
      <div
        role="toolbar"
        aria-label={t("roster.bulkActions")}
        className="flex flex-wrap items-center gap-2 rounded-xl border border-primary/25 bg-accent/45 p-2 text-sm"
      >
        <strong className="mr-1">{t("roster.selected", { count: selectedIds.length })}</strong>
        <form
          className="flex flex-wrap items-center gap-1.5 max-md:w-full max-md:flex-nowrap"
          onSubmit={(event) => {
            event.preventDefault();
            if (!moveTarget) return;
            onMoveRequest(
              selectedIds,
              Number(moveTarget),
              (event.nativeEvent as SubmitEvent).submitter,
            );
          }}
        >
          <NativeSelect
            className="w-44 max-md:w-full"
            aria-label={t("roster.target")}
            value={moveTarget}
            onChange={(event) => setMoveTarget(event.target.value)}
          >
            <option value="">{t("roster.target")}</option>
            {moveTargets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.name}
              </option>
            ))}
          </NativeSelect>
          <Button type="submit" size="sm" disabled={!moveTarget}>
            {t("roster.move")}
          </Button>
        </form>
        <form
          className="flex flex-wrap items-center gap-1.5 max-md:w-full max-md:flex-nowrap"
          onSubmit={(event) => {
            event.preventDefault();
            if (!bulkLanguage) return;
            setLanguages.mutate({
              path: { year_id: yearId },
              body: {
                student_ids: selectedIds,
                language: bulkLanguage === "none" ? null : bulkLanguage,
              },
            });
          }}
        >
          <NativeSelect
            className="w-48 max-md:w-full"
            aria-label={t("roster.bulkLanguage")}
            value={bulkLanguage}
            disabled={setLanguages.isPending}
            onChange={(event) => setBulkLanguage(event.target.value as Language | "none" | "")}
          >
            <option value="">{t("roster.bulkLanguage")}</option>
            <option value="none">{t("import.noLanguage")}</option>
            <option value="german" disabled={grade < 4}>
              {t("subjects.german")}
            </option>
            <option value="french" disabled={grade < 4}>
              {t("subjects.french")}
            </option>
          </NativeSelect>
          <Button
            type="submit"
            size="sm"
            variant="outline"
            disabled={!bulkLanguage}
            pending={setLanguages.isPending}
            pendingLabel={t("feedback.saving")}
          >
            {t("roster.applyLanguage")}
          </Button>
        </form>
        <Button
          className="ml-auto"
          size="sm"
          variant="ghost"
          onClick={() => setSelection(undefined)}
        >
          {t("roster.clearSelection")}
        </Button>
      </div>
    ) : null;

  return (
    <>
      {effectiveView === "cards" ? (
        // Phones: a card per student. Students move by ticking them and using the toolbar,
        // since dragging to a class tab needs a mouse.
        <div hidden={hidden} className="space-y-3">
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-card">
            {yearWritable ? (
              <label className="flex min-w-0 cursor-pointer items-center gap-3 text-sm font-medium">
                {selectAllCheckbox()}
                <span aria-hidden="true">{t("roster.selectAll")}</span>
              </label>
            ) : null}
            <span className="ml-auto shrink-0 text-xs text-muted-foreground tabular">
              {t("classWorkspace.studentCount", { count: roster.length })}
            </span>
          </div>
          {bulkToolbar}
          {rosterPending ? (
            <SkeletonStudentCards cards={4} columns={4} controls />
          ) : roster.length === 0 ? (
            <Card>
              <p className="p-8 text-center text-sm text-muted-foreground">{t("roster.empty")}</p>
            </Card>
          ) : (
            <StudentGradeCards
              ariaLabel={t("classWorkspace.tableLabel")}
              emptyColumnsLabel={t("columns.empty")}
              columns={visibleColumns.map((column) => ({
                id: column.id,
                label: column.name,
                meta: t(`roles.${column.owner_role}`),
              }))}
              students={roster.map((student) => ({
                id: student.student_id,
                fullName: student.full_name,
                leadingControl: yearWritable ? selectStudentCheckbox(student) : undefined,
                headerControls: (
                  <>
                    {schoolNumberInput(student, "w-20 shrink-0 px-2 text-center tabular")}
                    {languageSelect(student, "flex-1")}
                  </>
                ),
                values: visibleColumns.map((column) => ({
                  columnId: column.id,
                  value: (
                    <span
                      className="text-muted-foreground"
                      title={t("classWorkspace.gradeEntryInTeacher")}
                    >
                      —
                    </span>
                  ),
                })),
              }))}
            />
          )}
          {yearWritable ? (
            <Card className="border-success/30 bg-success-surface/35 p-3">
              <form className="flex flex-col gap-2" onSubmit={addRosterStudent}>
                <div className="grid grid-cols-2 gap-2">
                  {studentNumberField("tabular")}
                  {studentNameField()}
                </div>
                {studentLanguageField("max-md:w-full")}
                {addStudentButton("w-full")}
              </form>
            </Card>
          ) : null}
        </div>
      ) : (
        <>
          {bulkToolbar}
          <TableScroll
            hidden={hidden}
            data-testid="class-roster-surface"
            data-drag-scroll
            aria-label={t("classWorkspace.tableLabel")}
            className="max-h-[70svh] rounded-xl border border-border bg-card shadow-card"
          >
            <table
              className="w-full table-fixed border-separate border-spacing-0 text-sm"
              style={{
                minWidth: `${pinned.handle + pinned.number + pinned.name + 10 + visibleColumns.length * 8}rem`,
              }}
            >
              <TableCaption>{t("classWorkspace.tableLabel")}</TableCaption>
              <colgroup>
                <col style={{ width: `${pinned.handle}rem` }} />
                <col style={{ width: `${pinned.number}rem` }} />
                <col style={{ width: `${pinned.name}rem` }} />
                <col style={{ width: "10rem" }} />
                {visibleColumns.map((column) => (
                  <col key={column.id} style={{ width: "8rem" }} />
                ))}
                {/* Absorbs leftover width so the pinned columns keep the exact
                    widths their sticky offsets assume. */}
                <col />
              </colgroup>
              <thead>
                <tr>
                  <th className="sticky top-0 left-0 z-40 border-b border-r border-border bg-muted p-1.5 text-left text-xs text-muted-foreground">
                    {yearWritable ? selectAllCheckbox("ml-1.5") : null}
                    <span className="sr-only">{t("classWorkspace.selectMoveColumn")}</span>
                  </th>
                  <th
                    className={`sticky top-0 ${pinned.numberLeft} z-40 border-b border-r border-border bg-muted p-2 text-left text-xs font-semibold text-muted-foreground`}
                  >
                    {t("students.schoolNumber")}
                  </th>
                  <th
                    className={`sticky top-0 ${pinned.nameLeft} z-40 border-b border-r border-border bg-muted p-2 text-left text-xs font-semibold text-muted-foreground`}
                  >
                    {t("students.fullName")}
                  </th>
                  <th className="sticky top-0 z-30 border-b border-border bg-muted p-2 text-left text-xs font-semibold text-muted-foreground">
                    {t("roster.language")}
                  </th>
                  <ClassColumnHeaders
                    columns={columns}
                    subject={subject}
                    semesterId={semesterId}
                    writable={columnsWritable}
                    onChanged={onColumnsChanged}
                    onRename={(column, opener) => {
                      renameFocus.remember(opener);
                      setRenaming(column);
                    }}
                  />
                  <th
                    aria-hidden="true"
                    className="sticky top-0 z-30 border-b border-border bg-muted"
                  />
                </tr>
              </thead>
              <tbody>
                {rosterPending ? (
                  <SkeletonTableRows columns={visibleColumns.length + 5} rows={8} />
                ) : roster.length === 0 ? (
                  <tr>
                    <td
                      colSpan={visibleColumns.length + 5}
                      className="p-10 text-center text-muted-foreground"
                    >
                      {t("roster.empty")}
                    </td>
                  </tr>
                ) : (
                  roster.map((student) => (
                    <tr
                      key={student.student_id}
                      className="group even:bg-muted/20 hover:bg-accent/45"
                    >
                      <td className="sticky left-0 z-20 border-b border-r border-border/70 bg-card p-1 group-even:bg-muted group-hover:bg-accent">
                        <div className="flex items-center gap-1">
                          {yearWritable ? selectStudentCheckbox(student, "ml-1.5") : null}
                          {/* Dragging to a class tab needs a mouse; phones move by selection. */}
                          {isPhone ? null : (
                            <button
                              type="button"
                              draggable={yearWritable}
                              className="grid size-7 max-w-full cursor-grab place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground active:cursor-grabbing"
                              aria-label={t("classWorkspace.moveStudent", {
                                name: student.full_name,
                              })}
                              onDragStart={(event) => {
                                event.dataTransfer.effectAllowed = "move";
                                event.dataTransfer.setData(
                                  "application/x-flrc-student-id",
                                  String(student.student_id),
                                );
                                setDraggedStudentId(student.student_id);
                              }}
                              onDragEnd={() => setDraggedStudentId(undefined)}
                            >
                              <GripVerticalIcon className="size-4" />
                            </button>
                          )}
                        </div>
                      </td>
                      <td
                        className={`sticky ${pinned.numberLeft} z-20 border-b border-r border-border/70 bg-card p-1 group-even:bg-muted group-hover:bg-accent`}
                      >
                        {schoolNumberInput(
                          student,
                          "h-8 w-full min-w-0 rounded-md px-2 text-center tabular max-md:h-10",
                        )}
                      </td>
                      <td
                        className={`sticky ${pinned.nameLeft} z-20 border-b border-r border-border/70 bg-card px-2 py-1.5 font-medium group-even:bg-muted group-hover:bg-accent`}
                        title={student.full_name}
                      >
                        {student.full_name}
                      </td>
                      <td className="border-b border-border/70 p-0.5">
                        {languageSelect(student, "h-8 w-full min-w-0 px-2 pr-6 text-xs")}
                      </td>
                      {visibleColumns.map((column) => (
                        <td
                          key={column.id}
                          className="border-b border-l border-border/70 px-0.5 py-1 text-center text-muted-foreground"
                        >
                          <span title={t("classWorkspace.gradeEntryInTeacher")}>—</span>
                        </td>
                      ))}
                      <td aria-hidden="true" className="border-b border-border/70" />
                    </tr>
                  ))
                )}
                {yearWritable ? (
                  <tr className="bg-success-surface/35">
                    <td className="border-r border-border bg-card p-1 text-center text-success">
                      <UserRoundPlusIcon className="mx-auto size-4" />
                    </td>
                    <td colSpan={visibleColumns.length + 4} className="p-2">
                      <form
                        className="flex flex-wrap items-center gap-2"
                        onSubmit={addRosterStudent}
                      >
                        {studentNumberField("w-28 tabular")}
                        {studentNameField("min-w-56 flex-1")}
                        {studentLanguageField("w-36")}
                        {addStudentButton()}
                      </form>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </TableScroll>
        </>
      )}
      <RenameFieldDialog
        column={renaming}
        semesterId={semesterId}
        finalFocus={renameFocus.finalFocus}
        onClose={() => setRenaming(undefined)}
        onRenamed={onColumnsChanged}
      />
    </>
  );
}
