import { create } from "zustand";
import type { GridOut } from "@flrc/api-client";

export type CellKey = `${number}:${number}`;
export const dirtyKey = (studentId: number, columnId: number): CellKey =>
  `${studentId}:${columnId}`;

export type DirtyCell = {
  studentId: number;
  columnId: number;
  value: number | string | null;
  expectedVersion: number;
};

type DirtyState = {
  cells: Record<CellKey, DirtyCell>;
  generation: number;
  setCell: (cell: DirtyCell) => void;
  setRatings: (grid: GridOut, value: 1 | 2 | 3, studentId?: number) => void;
  clearCells: (keys: CellKey[]) => void;
  clearAll: () => void;
};

export const useDirtyStore = create<DirtyState>((set) => ({
  cells: {},
  generation: 0,
  setCell: (cell) =>
    set((state) => ({
      cells: { ...state.cells, [dirtyKey(cell.studentId, cell.columnId)]: cell },
    })),
  setRatings: (grid, value, studentId) =>
    set((state) => {
      if (grid.meta.semester_status !== "open" || grid.meta.year_status !== "active") return state;
      const cells = { ...state.cells };
      const columns = grid.columns.filter((column) => column.value_type === "scale3");
      for (const row of grid.rows) {
        if (studentId !== undefined && row.student_id !== studentId) continue;
        for (const column of columns) {
          const key = dirtyKey(row.student_id, column.id);
          const saved = row.cells[String(column.id)];
          if (saved?.value === value) delete cells[key];
          else {
            cells[key] = {
              studentId: row.student_id,
              columnId: column.id,
              value,
              // Keep the original version of an existing draft, even after a refetch.
              expectedVersion: cells[key]?.expectedVersion ?? saved?.version ?? 0,
            };
          }
        }
      }
      return { cells };
    }),
  clearCells: (keys) =>
    set((state) => {
      const cells = { ...state.cells };
      keys.forEach((key) => delete cells[key]);
      return { cells };
    }),
  clearAll: () => set((state) => ({ cells: {}, generation: state.generation + 1 })),
}));
