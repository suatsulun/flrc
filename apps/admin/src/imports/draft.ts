import { createStore } from "zustand/vanilla";
import type { ImportClassMove, ImportLanguageChange, ImportStudentAdd } from "@flrc/api-client";

type Snapshot = {
  moves: Record<number, ImportClassMove>;
  additions: Record<number, ImportStudentAdd>;
  removed: number[];
  languages: Record<number, ImportLanguageChange>;
};
type ImportDraft = Snapshot & {
  history: Snapshot[];
  move: (change: ImportClassMove, originalClass: string) => void;
  add: (student: ImportStudentAdd) => void;
  remove: (schoolNumber: number) => void;
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
    move: (change, originalClass) =>
      set((state) => {
        const moves = { ...state.moves };
        if (`${change.grade_level}/${change.section}` === originalClass) {
          delete moves[change.school_number];
        } else {
          moves[change.school_number] = change;
        }
        return { moves, history: [...state.history, snapshot(state)] };
      }),
    add: (student) =>
      set((state) => ({
        additions: { ...state.additions, [student.school_number]: student },
        history: [...state.history, snapshot(state)],
      })),
    remove: (schoolNumber) =>
      set((state) => {
        const additions = { ...state.additions };
        const moves = { ...state.moves };
        const languages = { ...state.languages };
        const wasAdded = Boolean(additions[schoolNumber]);
        delete additions[schoolNumber];
        delete moves[schoolNumber];
        delete languages[schoolNumber];
        return {
          additions,
          moves,
          languages,
          removed: wasAdded ? state.removed : [...state.removed, schoolNumber],
          history: [...state.history, snapshot(state)],
        };
      }),
    setLanguage: (change) =>
      set((state) => ({
        languages: { ...state.languages, [change.school_number]: change },
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
