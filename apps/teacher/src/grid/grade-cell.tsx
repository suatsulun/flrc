import { useTranslation } from "react-i18next";
import type { GridColumnOut, GridRowOut } from "@flrc/api-client";
import {
  LockedCell,
  SCALE3_FACES,
  Scale3Cell,
  ScoreCell,
  TextCell,
  type CellValue,
} from "@flrc/ui/grid/cells";
import { dirtyKey, useDirtyStore } from "./dirty-store";
import { useGridKeyboard } from "./use-grid-keyboard";

type Navigation = ReturnType<typeof useGridKeyboard>;

export function GradeCell({
  column,
  row,
  rowIndex,
  columnIndex,
  readOnly,
  navigation,
  fit,
}: {
  column: GridColumnOut;
  row: GridRowOut;
  rowIndex?: number;
  columnIndex?: number;
  readOnly: boolean;
  navigation?: Navigation;
  fit?: boolean;
}) {
  const { t } = useTranslation();
  const key = dirtyKey(row.student_id, column.id);
  const dirtyCell = useDirtyStore((state) => state.cells[key]);
  const serverCell = row.cells[String(column.id)];
  const value = dirtyCell ? dirtyCell.value : (serverCell?.value ?? null);
  const label = `${row.full_name} — ${column.label}`;

  if (readOnly) {
    const displayValue =
      column.value_type === "scale3" && (value === 1 || value === 2 || value === 3)
        ? SCALE3_FACES[value]
        : value;
    return (
      <LockedCell
        value={displayValue}
        label={label}
        fit={fit}
        wide={column.value_type === "text"}
      />
    );
  }

  const commit = (next: CellValue) => {
    const serverValue = serverCell?.value ?? null;
    if (next === serverValue) useDirtyStore.getState().clearCells([key]);
    else {
      useDirtyStore.getState().setCell({
        studentId: row.student_id,
        columnId: column.id,
        value: next,
        expectedVersion: serverCell?.version ?? 0,
      });
    }
  };

  const navigable =
    rowIndex !== undefined && columnIndex !== undefined && navigation
      ? {
          onNavKey: navigation.onNavKey(rowIndex, columnIndex),
          cellRef: navigation.register(rowIndex, columnIndex),
        }
      : {};

  const props = {
    value,
    label,
    dirty: Boolean(dirtyCell),
    caution: !column.owned_by_you,
    onCommit: commit,
    fit,
    ...navigable,
  };

  if (column.value_type === "score") return <ScoreCell {...props} />;
  if (column.value_type === "scale3") {
    return (
      <Scale3Cell
        {...props}
        levelLabels={{
          1: t("grid.scaleLevels.1"),
          2: t("grid.scaleLevels.2"),
          3: t("grid.scaleLevels.3"),
        }}
      />
    );
  }
  return (
    <TextCell
      {...props}
      editorLabels={{
        title: label,
        description: t("grid.commentEditorDescription"),
        placeholder: t("grid.commentEditorPlaceholder"),
        empty: t("grid.addComment"),
        done: t("grid.commentEditorDone"),
      }}
    />
  );
}
