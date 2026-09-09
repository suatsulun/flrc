import { Skeleton } from "@flrc/ui/components/skeleton";
import { TableCaption, TableScroll } from "@flrc/ui/components/table";
import type { ColumnCreate } from "@flrc/api-client";
import {
  addAdminRosterStudentMutation,
  patchAdminRosterStudentMutation,
  type ColumnOut,
  type RosterStudentOut,
} from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { useMutation } from "@tanstack/react-query";
import { GripVerticalIcon, PlusIcon, UserRoundPlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ClassColumnHeaders } from "./ClassColumnHeaders";
type Subject = ColumnCreate["subject"];
/**
 * Pinned identity columns, in rem (ADR-045). The `left-10` / `left-38` sticky
 * offsets below are these widths, so they must stay in step; the trailing slack
 * column keeps the declared widths exact instead of stretching them.
 */
const ROSTER_HANDLE_REM = 2.5;
const ROSTER_NUMBER_REM = 7;
const ROSTER_NAME_REM = 14;
const ROSTER_IDENTITY_REM = ROSTER_HANDLE_REM + ROSTER_NUMBER_REM + ROSTER_NAME_REM;

export function ClassRosterTable({
  classId,
  grade,
  subject,
  semesterId,
  roster,
  rosterPending,
  columns,
  yearWritable,
  columnsWritable,
  setDraggedStudentId,
  onRosterChanged,
  onColumnsChanged,
  hidden,
}: {
  classId: number;
  grade: number;
  subject: Subject;
  semesterId?: number;
  roster: RosterStudentOut[];
  rosterPending: boolean;
  columns: ColumnOut[];
  yearWritable: boolean;
  columnsWritable: boolean;
  hidden: boolean;
  setDraggedStudentId: (id: number | undefined) => void;
  onRosterChanged: () => Promise<unknown>;
  onColumnsChanged: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const visibleColumns = columns.filter((column) => column.is_active);
  const [studentNumber, setStudentNumber] = useState("");
  const [studentName, setStudentName] = useState("");
  const [studentLanguage, setStudentLanguage] = useState<"german" | "french" | "">("");
  const addStudent = useMutation({
    ...addAdminRosterStudentMutation(),
    onSuccess: () => {
      setStudentNumber("");
      setStudentName("");
      toast.success(t("classWorkspace.studentAdded"));
      void onRosterChanged();
    },
  });
  const patchStudent = useMutation({
    ...patchAdminRosterStudentMutation(),
    onSuccess: () => {
      toast.success(t("feedback.saved"));
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

  return (
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
          minWidth: `${ROSTER_IDENTITY_REM + 10 + visibleColumns.length * 8}rem`,
        }}
      >
        <TableCaption>{t("classWorkspace.tableLabel")}</TableCaption>
        <colgroup>
          <col style={{ width: `${ROSTER_HANDLE_REM}rem` }} />
          <col style={{ width: `${ROSTER_NUMBER_REM}rem` }} />
          <col style={{ width: `${ROSTER_NAME_REM}rem` }} />
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
              <span className="sr-only">{t("classWorkspace.moveStudent")}</span>
            </th>
            <th className="sticky top-0 left-10 z-40 border-b border-r border-border bg-muted p-2 text-left text-xs font-semibold text-muted-foreground">
              {t("students.schoolNumber")}
            </th>
            <th className="sticky top-0 left-38 z-40 border-b border-r border-border bg-muted p-2 text-left text-xs font-semibold text-muted-foreground">
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
            />
            <th aria-hidden="true" className="sticky top-0 z-30 border-b border-border bg-muted" />
          </tr>
        </thead>
        <tbody>
          {rosterPending ? (
            <tr aria-label={t("loading")}>
              <td colSpan={visibleColumns.length + 5} className="space-y-2 p-4">
                {Array.from({ length: 5 }, (_, index) => (
                  <Skeleton key={index} className="h-9 w-full" />
                ))}
              </td>
            </tr>
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
              <tr key={student.student_id} className="group even:bg-muted/20 hover:bg-accent/45">
                <td className="sticky left-0 z-20 border-b border-r border-border/70 bg-card p-1 group-even:bg-muted group-hover:bg-accent">
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
                </td>
                <td className="sticky left-10 z-20 border-b border-r border-border/70 bg-card p-1 group-even:bg-muted group-hover:bg-accent">
                  <Input
                    className="h-8 w-full min-w-0 rounded-md px-2 text-center tabular"
                    inputMode="numeric"
                    aria-label={`${student.full_name} — ${t("students.schoolNumber")}`}
                    defaultValue={student.school_number ?? ""}
                    disabled={!yearWritable || patchStudent.isPending}
                    onBlur={(event) => {
                      const value = event.currentTarget.value.trim();
                      const next = value ? Number(value) : null;
                      if (next === student.school_number) return;
                      patchStudent.mutate({
                        path: {
                          class_id: classId,
                          student_id: student.student_id,
                        },
                        body: { school_number: next },
                      });
                    }}
                  />
                </td>
                <td
                  className="sticky left-38 z-20 border-b border-r border-border/70 bg-card px-2 py-1.5 font-medium group-even:bg-muted group-hover:bg-accent"
                  title={student.full_name}
                >
                  {student.full_name}
                </td>
                <td className="border-b border-border/70 p-0.5">
                  <NativeSelect
                    className="h-8 w-full min-w-0 px-2 pr-6 text-xs"
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
                          language: (event.target.value || null) as "german" | "french" | null,
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
                <form className="flex flex-wrap items-center gap-2" onSubmit={addRosterStudent}>
                  <Input
                    className="w-28 tabular"
                    type="number"
                    min="1"
                    required
                    value={studentNumber}
                    onChange={(event) => setStudentNumber(event.target.value)}
                    placeholder={t("students.schoolNumber")}
                    aria-label={t("students.schoolNumber")}
                  />
                  <Input
                    className="min-w-56 flex-1"
                    required
                    value={studentName}
                    onChange={(event) => setStudentName(event.target.value)}
                    placeholder={t("students.fullName")}
                    aria-label={t("students.fullName")}
                  />
                  {grade >= 4 ? (
                    <NativeSelect
                      className="w-36"
                      aria-label={t("roster.language")}
                      value={studentLanguage}
                      onChange={(event) =>
                        setStudentLanguage(event.target.value as "german" | "french" | "")
                      }
                    >
                      <option value="">{t("roster.language")}</option>
                      <option value="german">{t("subjects.german")}</option>
                      <option value="french">{t("subjects.french")}</option>
                    </NativeSelect>
                  ) : null}
                  <Button
                    type="submit"
                    pending={addStudent.isPending}
                    pendingLabel={t("feedback.saving")}
                  >
                    <PlusIcon />
                    {t("classWorkspace.addStudent")}
                  </Button>
                </form>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </TableScroll>
  );
}
