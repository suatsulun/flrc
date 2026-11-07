import { useCallback, useSyncExternalStore, type KeyboardEvent, type ReactNode } from "react";

import { Card } from "#components/card";
import { Segmented } from "#components/segmented";
import { useIsPhone } from "#hooks/use-is-phone";
import { cn } from "#lib/utils";

/*
 * A grade table's phone layout (`< 768px`): one card per student listing every sütun and its
 * value top to bottom, so nothing scrolls sideways. People can still switch to the table on a
 * phone; that choice is shared by every grade table and kept per browser.
 */

export type GradeTableView = "cards" | "table";

export const GRADE_VIEW_STORAGE_KEY = "flrc-grade-phone-view";
const GRADE_VIEW_EVENT = "flrc-grade-view-change";

/** The stored phone view; `"cards"` when nothing (or nothing readable) is stored. */
export function readGradeTableView(): GradeTableView {
  try {
    return window.localStorage.getItem(GRADE_VIEW_STORAGE_KEY) === "table" ? "table" : "cards";
  } catch {
    return "cards";
  }
}

// The page's current choice. Storage only seeds it, so the switch still works for the visit
// where storage is unavailable (hardened or private browsers).
let currentView: GradeTableView | null = null;

function gradeViewSnapshot(): GradeTableView {
  currentView ??= readGradeTableView();
  return currentView;
}

/** Stores the phone view and tells every `useGradeTableView` on the page. */
export function storeGradeTableView(view: GradeTableView): void {
  currentView = view;
  try {
    window.localStorage.setItem(GRADE_VIEW_STORAGE_KEY, view);
  } catch {
    // Not persisted; the choice still holds until the page reloads.
  }
  window.dispatchEvent(new Event(GRADE_VIEW_EVENT));
}

function subscribeGradeView(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key !== GRADE_VIEW_STORAGE_KEY) return;
    currentView = readGradeTableView();
    onChange();
  };
  window.addEventListener(GRADE_VIEW_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(GRADE_VIEW_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

/**
 * The grade-table view to render. Wider screens always get the table; phones get the stored
 * choice, cards by default. Mount only `effectiveView`'s layout so form controls exist once.
 */
export function useGradeTableView(): {
  isPhone: boolean;
  view: GradeTableView;
  setView: (next: GradeTableView) => void;
  /** `"table"` when `!isPhone`; otherwise the user's persisted phone `view` (default `"cards"`). */
  effectiveView: GradeTableView;
} {
  const isPhone = useIsPhone();
  const view = useSyncExternalStore(subscribeGradeView, gradeViewSnapshot);
  const setView = useCallback((next: GradeTableView) => storeGradeTableView(next), []);
  return { isPhone, view, setView, effectiveView: isPhone ? view : "table" };
}

/** "Kartlar | Tablo" for phones; hidden from `md` up, where the table is the only view. */
export function GradeViewSwitch({
  value,
  onChange,
  labels,
  className,
}: {
  value: GradeTableView;
  onChange: (value: GradeTableView) => void;
  labels: {
    ariaLabel: string;
    cards: string;
    table: string;
  };
  className?: string;
}) {
  return (
    <Segmented<GradeTableView>
      ariaLabel={labels.ariaLabel}
      value={value}
      onChange={onChange}
      options={[
        { value: "cards", label: labels.cards },
        { value: "table", label: labels.table },
      ]}
      className={cn("md:hidden", className)}
    />
  );
}

export type StudentGradeCardColumn = {
  id: number | string;
  label: string;
  group?: string | null;
  /** A detail under the label, e.g. the role responsible for the sütun. */
  meta?: ReactNode;
};

export type StudentGradeCardItem = {
  id: number | string;
  schoolNumber?: number | string | null;
  fullName: string;
  /** Shown on the right of the name, e.g. the student's position in the class. */
  badge?: ReactNode;
  /** Shown before the name, e.g. a selection checkbox. */
  leadingControl?: ReactNode;
  /** A row of controls under the name, e.g. editable school number and language. */
  headerControls?: ReactNode;
  values: ReadonlyArray<{
    columnId: number | string;
    value: ReactNode;
  }>;
};

/** Longer text values (comments) go under their label at full width instead of beside it. */
const INLINE_VALUE_MAX = 24;

/** Consecutive columns sharing a `group`, so each group gets one heading. */
function columnRuns(columns: ReadonlyArray<StudentGradeCardColumn>) {
  const runs: Array<{ group: string | null; columns: StudentGradeCardColumn[] }> = [];
  for (const column of columns) {
    const group = column.group || null;
    const last = runs.at(-1);
    if (last && last.group === group) last.columns.push(column);
    else runs.push({ group, columns: [column] });
  }
  return runs;
}

/** Arrow keys move the reading mark from one student card to the next. */
function moveMark(event: KeyboardEvent<HTMLElement>) {
  if (event.target !== event.currentTarget) return;
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const item = event.currentTarget.parentElement;
  const sibling =
    event.key === "ArrowDown" ? item?.nextElementSibling : item?.previousElementSibling;
  const next = sibling?.firstElementChild;
  if (!(next instanceof HTMLElement)) return;
  event.preventDefault();
  next.focus();
}

/**
 * One card per student with every sütun and its value, for grade tables on phones. With
 * `interactiveRowMarks`, the student a teacher taps (or reaches with the arrow keys) stays
 * marked like the class sheet's active row.
 */
export function StudentGradeCards({
  ariaLabel,
  students,
  columns,
  emptyColumnsLabel,
  interactiveRowMarks = false,
  className,
}: {
  ariaLabel: string;
  students: ReadonlyArray<StudentGradeCardItem>;
  columns: ReadonlyArray<StudentGradeCardColumn>;
  emptyColumnsLabel?: ReactNode;
  /** Enables click/focus and ArrowUp/ArrowDown reading mark (`class-report`). */
  interactiveRowMarks?: boolean;
  className?: string;
}) {
  const runs = columnRuns(columns);

  return (
    <ul aria-label={ariaLabel} className={cn("min-w-0 space-y-3", className)}>
      {students.map((student) => {
        const values = new Map(student.values.map((item) => [item.columnId, item.value]));
        const hasNumber = student.schoolNumber != null && student.schoolNumber !== "";
        return (
          <li key={student.id} className="min-w-0">
            <Card
              data-testid="student-grade-card"
              className={cn(
                "overflow-hidden",
                interactiveRowMarks &&
                  "scroll-mt-[calc(var(--app-shell-header-height,3.5rem)_+_1rem)] cursor-pointer outline-none focus:bg-[var(--row-active)] focus:shadow-[inset_4px_0_0_var(--row-active-edge)] focus:[--muted-foreground:var(--row-active-muted-foreground)]",
              )}
              tabIndex={interactiveRowMarks ? 0 : undefined}
              aria-label={interactiveRowMarks ? student.fullName : undefined}
              onKeyDown={interactiveRowMarks ? moveMark : undefined}
            >
              <header className="space-y-2.5 border-b border-border bg-muted/40 px-4 py-3">
                <div className="flex items-center gap-3">
                  {student.leadingControl ? (
                    <span className="flex shrink-0 items-center">{student.leadingControl}</span>
                  ) : null}
                  {hasNumber ? (
                    <span className="tabular shrink-0 rounded-md border border-border bg-card px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
                      {student.schoolNumber}
                    </span>
                  ) : null}
                  <p className="min-w-0 flex-1 text-sm font-semibold break-words">
                    {student.fullName}
                  </p>
                  {student.badge ? <span className="shrink-0">{student.badge}</span> : null}
                </div>
                {student.headerControls ? (
                  <div className="flex flex-wrap items-center gap-2">{student.headerControls}</div>
                ) : null}
              </header>
              {columns.length === 0 ? (
                emptyColumnsLabel ? (
                  <p className="px-4 py-3 text-sm text-muted-foreground">{emptyColumnsLabel}</p>
                ) : null
              ) : (
                <div className="divide-y divide-border">
                  {runs.map((run) => (
                    <div key={run.columns[0].id}>
                      {run.group ? (
                        <p className="px-4 pt-2.5 text-[0.6875rem] font-medium tracking-wide break-words text-muted-foreground uppercase">
                          {run.group}
                        </p>
                      ) : null}
                      <dl className="divide-y divide-border">
                        {run.columns.map((column) => {
                          const value = values.get(column.id);
                          const empty = value == null || value === "";
                          const stacked =
                            typeof value === "string" && value.length > INLINE_VALUE_MAX;
                          return (
                            <div
                              key={column.id}
                              className={cn(
                                "px-4 py-2.5 text-sm",
                                stacked ? "space-y-1" : "flex items-start justify-between gap-4",
                              )}
                            >
                              <dt className="min-w-0 break-words">
                                {column.label}
                                {column.meta ? (
                                  <span className="mt-0.5 block text-xs text-muted-foreground">
                                    {column.meta}
                                  </span>
                                ) : null}
                              </dt>
                              <dd
                                className={cn(
                                  stacked
                                    ? "break-words whitespace-pre-wrap"
                                    : "tabular shrink-0 text-right font-medium",
                                  empty && "text-muted-foreground",
                                )}
                              >
                                {empty ? "—" : value}
                              </dd>
                            </div>
                          );
                        })}
                      </dl>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
