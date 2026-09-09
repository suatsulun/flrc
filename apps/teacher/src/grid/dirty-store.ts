import { create } from "zustand";

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
  clearCells: (keys) =>
    set((state) => {
      const cells = { ...state.cells };
      keys.forEach((key) => delete cells[key]);
      return { cells };
    }),
  clearAll: () => set((state) => ({ cells: {}, generation: state.generation + 1 })),
}));
