import type { AppliedOut, GridOut, SaveCellIn } from "@flrc/api-client";
import { dirtyKey, type CellKey, type DirtyCell } from "./dirty-store";

/** Confirm submitted values, then rebase any newer edits onto the returned versions. */
export function mergeSavedGrid(
  grid: GridOut,
  draft: Record<CellKey, DirtyCell>,
  submitted: { cells: SaveCellIn[]; draft: Record<CellKey, DirtyCell> },
  applied: AppliedOut[],
) {
  const dirty = { ...draft };
  const sent = new Map(
    submitted.cells.map((cell) => [dirtyKey(cell.student_id, cell.column_id), cell]),
  );
  const rows = new Map(
    grid.rows.map((row) => [row.student_id, { ...row, cells: { ...row.cells } }]),
  );

  for (const update of applied) {
    const key = dirtyKey(update.student_id, update.column_id);
    const input = sent.get(key);
    const row = rows.get(update.student_id);
    if (!input || !row) continue;
    // No new edit means the submitted value wins, including an explicit null.
    // Removing a previously present draft means reverting to the old server value.
    const latest =
      draft[key] === submitted.draft[key]
        ? input.value
        : draft[key]
          ? draft[key].value
          : (row.cells[update.column_id]?.value ?? null);
    row.cells[update.column_id] = { value: input.value, version: update.version };
    if (latest === input.value) delete dirty[key];
    else {
      dirty[key] = {
        studentId: update.student_id,
        columnId: update.column_id,
        value: latest,
        expectedVersion: update.version,
      };
    }
  }
  return { grid: { ...grid, rows: [...rows.values()] }, dirty };
}
