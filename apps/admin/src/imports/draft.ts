import { createStore } from "zustand/vanilla";
import type { ImportClassMove, ImportLanguageChange, ImportStudentAdd } from "@flrc/api-client";

/** Grades 0–4 are primary school; grades 5–8 are middle school. */
const MIDDLE_START_GRADE = 5;

/**
 * Stable review identity of a manually added row: the stage of its chosen class plus its
 * number, matching the server's derived `row_key`. Later class moves never change it.
 */
export function additionRowKey(student: Pick<ImportStudentAdd, "grade_level" | "school_number">) {
  const stage = student.grade_level < MIDDLE_START_GRADE ? "primary" : "middle";
  return `${stage}:${student.school_number}`;
}

/** Deterministic order for serialized edits, so equal drafts share a preview query key. */
export function compareRowKeys(a: string, b: string) {
  return a < b ? -1 : a > b ? 1 : 0;
}

type Snapshot = {
  moves: Record<string, ImportClassMove>;
  additions: Record<string, ImportStudentAdd>;
  removed: string[];
  languages: Record<string, ImportLanguageChange>;
};
type ImportDraft = Snapshot & {
  history: Snapshot[];
  move: (change: ImportClassMove, original: { grade_level: number; section: string }) => void;
  add: (student: ImportStudentAdd) => void;
  remove: (rowKey: string) => void;
  setLanguage: (change: ImportLanguageChange) => void;
  undo: () => void;
  reset: () => void;
};
const empty = (): Snapshot => ({ moves: {}, additions: {}, removed: [], languages: {} });
const snapshot = ({ moves, additions, removed, languages }: Snapshot): Snapshot => ({
  moves,
  additions,
  removed,
  languages,
});

/** One in-memory draft per file/year review; server previews remain in Query. */
export function createImportDraft() {
  return createStore<ImportDraft>((set) => ({
    ...empty(),
    history: [],
    move: (change, original) =>
      set((state) => {
        const moves = { ...state.moves };
        if (change.grade_level === original.grade_level && change.section === original.section) {
          delete moves[change.row_key];
        } else {
          moves[change.row_key] = change;
        }
        return { moves, history: [...state.history, snapshot(state)] };
      }),
    add: (student) =>
      set((state) => ({
        additions: { ...state.additions, [additionRowKey(student)]: student },
        history: [...state.history, snapshot(state)],
      })),
    remove: (rowKey) =>
      set((state) => {
        const additions = { ...state.additions };
        const moves = { ...state.moves };
        const languages = { ...state.languages };
        const wasAdded = Boolean(additions[rowKey]);
        delete additions[rowKey];
        delete moves[rowKey];
        delete languages[rowKey];
        return {
          additions,
          moves,
          languages,
          removed: wasAdded ? state.removed : [...state.removed, rowKey],
          history: [...state.history, snapshot(state)],
        };
      }),
    setLanguage: (change) =>
      set((state) => ({
        languages: { ...state.languages, [change.row_key]: change },
        history: [...state.history, snapshot(state)],
      })),
    undo: () =>
      set((state) => ({
        ...(state.history.at(-1) ?? snapshot(state)),
        history: state.history.slice(0, -1),
      })),
    reset: () => set({ ...empty(), history: [] }),
  }));
}
