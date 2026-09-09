import type { ColumnCreate } from "@flrc/api-client";
import { createColumnMutation, type ColumnOut } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { useMutation } from "@tanstack/react-query";
import { Columns3Icon, PlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
type Subject = ColumnCreate["subject"];
type Role = ColumnCreate["owner_role"];
type ValueType = ColumnCreate["value_type"];

export function ClassAddColumn({
  grade,
  subject,
  semesterId,
  columns,
  writable,
  columnOwner,
  setColumnOwner,
  onChanged,
}: {
  grade: number;
  subject: Subject;
  semesterId?: number;
  columns: ColumnOut[];
  writable: boolean;
  columnOwner: Role;
  setColumnOwner: (role: Role) => void;
  onChanged: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const visibleColumns = columns.filter((column) => column.is_active);
  const scaleOnly = grade === 4 && subject !== "english";
  const [addingColumn, setAddingColumn] = useState(false);
  const [columnLabel, setColumnLabel] = useState("");
  const [columnType, setColumnType] = useState<ValueType>("score");
  const ownerRoles: Role[] = subject === "english" ? ["main", "skills"] : [subject];
  const createColumn = useMutation({
    ...createColumnMutation(),
    onSuccess: () => {
      setColumnLabel("");
      setAddingColumn(false);
      toast.success(t("classWorkspace.columnAdded"));
      void onChanged();
    },
  });
  function addColumn(event: FormEvent) {
    event.preventDefault();
    if (!semesterId || !columnLabel.trim()) return;
    createColumn.mutate({
      query: { semester_id: semesterId },
      body: {
        grade_level: grade,
        subject,
        value_type: scaleOnly ? "scale3" : columnType,
        owner_role: columnOwner,
        labels: { tr: columnLabel.trim(), en: "", de: "", fr: "" },
        counts_in_average: !scaleOnly && columnType === "score",
      },
    });
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Columns3Icon className="size-4 text-muted-foreground" />
        <strong className="text-sm">{t("classWorkspace.columns")}</strong>
        <Badge tone="neutral">{visibleColumns.length}</Badge>
        {writable ? (
          <Button
            className="ml-auto"
            size="sm"
            variant={addingColumn ? "secondary" : "outline"}
            onClick={() => setAddingColumn((value) => !value)}
          >
            <PlusIcon />
            {t("classWorkspace.addColumn")}
          </Button>
        ) : (
          <Badge tone="neutral">{t("classWorkspace.readOnly")}</Badge>
        )}
      </div>

      {scaleOnly ? (
        <p className="text-sm text-muted-foreground">{t("grid.gradeFourScaleOnly")}</p>
      ) : null}
      {addingColumn && semesterId ? (
        <form
          className="grid gap-2 rounded-lg border border-primary/25 bg-accent/45 p-2 sm:grid-cols-[minmax(12rem,1fr)_10rem_10rem_auto]"
          onSubmit={addColumn}
        >
          <Input
            autoFocus
            required
            value={columnLabel}
            onChange={(event) => setColumnLabel(event.target.value)}
            placeholder={t("classWorkspace.columnName")}
            aria-label={t("classWorkspace.columnName")}
          />
          <NativeSelect
            aria-label={t("classWorkspace.columnType")}
            value={scaleOnly ? "scale3" : columnType}
            disabled={scaleOnly}
            onChange={(event) => setColumnType(event.target.value as ValueType)}
          >
            {!scaleOnly ? <option value="score">{t("classWorkspace.typeScore")}</option> : null}
            <option value="scale3">{t("classWorkspace.typeScale")}</option>
            {!scaleOnly ? <option value="text">{t("classWorkspace.typeText")}</option> : null}
          </NativeSelect>
          <NativeSelect
            aria-label={t("classWorkspace.columnOwner")}
            value={columnOwner}
            onChange={(event) => setColumnOwner(event.target.value as Role)}
          >
            {ownerRoles.map((role) => (
              <option key={role} value={role}>
                {t(`roles.${role}`)}
              </option>
            ))}
          </NativeSelect>
          <Button
            type="submit"
            pending={createColumn.isPending}
            pendingLabel={t("feedback.saving")}
          >
            <PlusIcon />
            {t("forms.add")}
          </Button>
        </form>
      ) : null}
    </>
  );
}
