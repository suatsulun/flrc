import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import {
  deleteColumnMutation,
  removeAdminRosterStudentMutation,
  type ColumnOut,
  type RosterStudentOut,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { ConfirmDialog } from "@flrc/ui/components/dialog";
import { Input } from "@flrc/ui/components/input";

type Target = { kind: "student" | "column"; id: number; label: string };

export function ClassRemovePanel({
  classId,
  className,
  semesterId,
  grade,
  subject,
  roster,
  columns,
  yearWritable,
  columnsWritable,
  onRosterChanged,
  onColumnsChanged,
}: {
  classId: number;
  className: string;
  semesterId?: number;
  grade: number;
  subject: string;
  roster: RosterStudentOut[];
  columns: ColumnOut[];
  yearWritable: boolean;
  columnsWritable: boolean;
  onRosterChanged: () => Promise<unknown>;
  onColumnsChanged: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const [target, setTarget] = useState<Target>();
  const [search, setSearch] = useState("");
  const removeStudent = useMutation({
    ...removeAdminRosterStudentMutation(),
    onSuccess: async () => {
      setTarget(undefined);
      toast.success(t("classWorkspace.studentRemoved"));
      await onRosterChanged();
    },
  });
  const removeColumn = useMutation({
    ...deleteColumnMutation(),
    onSuccess: async (result) => {
      setTarget(undefined);
      toast.success(result.disabled ? t("columns.disabledInfo") : t("columns.deletedInfo"));
      await onColumnsChanged();
    },
  });
  const pending = removeStudent.isPending || removeColumn.isPending;
  const visibleStudents = roster.filter((s) =>
    `${s.school_number ?? ""} ${s.full_name}`
      .toLocaleLowerCase("tr")
      .includes(search.toLocaleLowerCase("tr")),
  );
  return (
    <div className="grid items-start gap-4 xl:grid-cols-2" data-testid="class-remove-panel">
      <Card>
        <CardHeader>
          <CardTitle>{t("classWorkspace.removeColumns")}</CardTitle>
          <Badge tone="neutral">{columns.filter((c) => c.is_active).length}</Badge>
        </CardHeader>
        <CardBody className="p-3">
          <p className="mb-3 text-sm text-muted-foreground">
            {t("classWorkspace.columnScope", { grade, subject: t(`subjects.${subject}`) })}
          </p>
          <ul className="divide-y divide-border">
            {columns.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-3 py-3"
                data-testid="remove-column-row"
              >
                <div className="min-w-0 flex-1">
                  <span className="block font-medium break-words">{c.labels.tr}</span>
                  <span className="text-xs text-muted-foreground">
                    {t(`columns.valueTypes.${c.value_type}`)} · {t(`roles.${c.owner_role}`)}
                  </span>
                </div>
                {c.is_active ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!columnsWritable || pending}
                    aria-label={t("classWorkspace.removeColumnLabel", { name: c.labels.tr })}
                    onClick={() => setTarget({ kind: "column", id: c.id, label: c.labels.tr })}
                  >
                    <Trash2Icon />
                    {t("classWorkspace.remove")}
                  </Button>
                ) : (
                  <Badge tone="neutral">{t("columns.disabled")}</Badge>
                )}
              </li>
            ))}
          </ul>
          {!columns.length ? (
            <p className="py-4 text-sm text-muted-foreground">{t("columns.empty")}</p>
          ) : null}
          {!columnsWritable ? (
            <p className="mt-3 text-sm text-muted-foreground">{t("classWorkspace.readOnly")}</p>
          ) : null}
        </CardBody>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("classWorkspace.removeStudents")}</CardTitle>
          <Badge tone="neutral">{roster.length}</Badge>
        </CardHeader>
        <CardBody className="p-3">
          <p className="mb-3 text-sm text-muted-foreground">
            {t("classWorkspace.removeStudentsHint", { className })}
          </p>
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label={t("import.search")}
            placeholder={t("import.search")}
          />
          <ul className="divide-y divide-border">
            {visibleStudents.map((s) => (
              <li
                key={s.student_id}
                className="flex items-center gap-3 py-3"
                data-testid="remove-student-row"
              >
                <div className="min-w-0 flex-1">
                  <span className="block font-medium break-words">{s.full_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {s.school_number ?? "—"} ·{" "}
                    {s.language ? t(`subjects.${s.language}`) : t("import.noLanguage")}
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!yearWritable || pending}
                  aria-label={t("classWorkspace.removeStudentLabel", { name: s.full_name })}
                  onClick={() =>
                    setTarget({ kind: "student", id: s.student_id, label: s.full_name })
                  }
                >
                  <Trash2Icon />
                  {t("classWorkspace.remove")}
                </Button>
              </li>
            ))}
          </ul>
          {!visibleStudents.length ? (
            <p className="py-4 text-sm text-muted-foreground">{t("import.noMatches")}</p>
          ) : null}
        </CardBody>
      </Card>
      <ConfirmDialog
        open={Boolean(target)}
        onOpenChange={(open) => {
          if (!open && !pending) setTarget(undefined);
        }}
        title={t(
          target?.kind === "student"
            ? "classWorkspace.removeStudents"
            : "classWorkspace.removeColumns",
        )}
        description={
          target?.kind === "student"
            ? t("classWorkspace.removeStudentConfirm", { name: target.label, className })
            : `${t("columns.deleteConfirm", { label: target?.label })} ${t("classWorkspace.columnScope", { grade, subject: t(`subjects.${subject}`) })}`
        }
        cancelLabel={t("forms.cancel")}
        confirmLabel={t("classWorkspace.remove")}
        destructive
        pending={pending}
        pendingLabel={t("feedback.saving")}
        onConfirm={() => {
          if (!target) return;
          if (target.kind === "student")
            removeStudent.mutate({ path: { class_id: classId, student_id: target.id } });
          else if (semesterId)
            removeColumn.mutate({
              path: { column_id: target.id },
              query: { semester_id: semesterId },
            });
        }}
      />
    </div>
  );
}
