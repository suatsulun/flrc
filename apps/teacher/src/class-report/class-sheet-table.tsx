import type { ClassSheetOut } from "@flrc/api-client";
import { useIsPhone } from "@flrc/ui/hooks/use-is-phone";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import "./class-sheet.css";

/* The pinned number and name columns, narrower on phones so the grades keep room to scroll. */
const NUMBER_WIDTH = 64;
const NAME_WIDTH = 240;
const PHONE_NUMBER_WIDTH = 48;
const PHONE_NAME_WIDTH = 136;
const FIELD_MIN_WIDTH = 72;

function groupSpans(columns: ClassSheetOut["columns"]) {
  const spans: Array<{ group: string | null; span: number; key: number }> = [];
  for (const column of columns) {
    const last = spans.at(-1);
    if (last && last.group === column.group) last.span += 1;
    else spans.push({ group: column.group, span: 1, key: column.id });
  }
  return spans.some((item) => item.group) ? spans : [];
}

/** Arrow keys move the reading mark from one student to the next. */
function moveMark(event: KeyboardEvent<HTMLTableRowElement>) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const next =
    event.key === "ArrowDown"
      ? event.currentTarget.nextElementSibling
      : event.currentTarget.previousElementSibling;
  if (!(next instanceof HTMLTableRowElement)) return;
  event.preventDefault();
  next.focus();
}

/** What 3, 2 and 1 mean, under a sheet (or its phone cards) that has 1-2-3 assessments. */
export function ClassSheetScaleLegend({ columns }: { columns: ClassSheetOut["columns"] }) {
  const { t } = useTranslation();
  if (!columns.some((column) => column.value_type === "scale3")) return null;
  return (
    <p className="flex flex-wrap gap-x-5 gap-y-1 rounded-xl border border-border bg-card px-4 py-3 text-xs text-muted-foreground shadow-card">
      {([3, 2, 1] as const).map((level) => (
        <span key={level}>
          <span className="font-semibold text-foreground">{level}</span> ·{" "}
          {t(`grid.scaleLevels.${level}`)}
        </span>
      ))}
    </p>
  );
}

/**
 * The on-screen twin of the printed class sheet: the same columns in the same order
 * from the same endpoint. Students alternate in shade, and the student a teacher
 * clicks (or reaches with the arrow keys) stays marked while they talk. The number
 * and name stay pinned while the grades scroll sideways.
 */
export function ClassSheetTable({ sheet }: { sheet: ClassSheetOut }) {
  const { t } = useTranslation();
  const isPhone = useIsPhone();
  const surface = useRef<HTMLDivElement>(null);
  const [surfaceWidth, setSurfaceWidth] = useState(0);
  const spans = groupSpans(sheet.columns);
  const headTop = { top: "var(--app-shell-header-height, 3.5rem)" };
  const numberWidth = isPhone ? PHONE_NUMBER_WIDTH : NUMBER_WIDTH;
  const nameWidth = isPhone ? PHONE_NAME_WIDTH : NAME_WIDTH;
  // The name column's offset is the number column's width.
  const nameLeft = isPhone ? "left-12" : "left-16";
  // Only phones pin number and name while the grades scroll sideways under them; wider screens
  // keep the sheet as it was. The pinned name column draws its own edge.
  const pinHead = isPhone ? "sticky z-20" : "";
  const pinCell = isPhone ? "sticky z-10" : "";
  const pinnedEdge = isPhone ? "border-r" : "";
  const minWidth = numberWidth + nameWidth + FIELD_MIN_WIDTH * sheet.columns.length;
  // A table that fits keeps its heading pinned below the page header; a wider one
  // (phones) scrolls sideways inside its card instead.
  const scrolls = surfaceWidth > 0 && surfaceWidth < minWidth;

  useEffect(() => {
    const element = surface.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setSurfaceWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="space-y-3">
      <div
        ref={surface}
        className={`w-full min-w-0 rounded-xl border border-border bg-card shadow-card ${scrolls ? "overflow-x-auto" : "overflow-visible"}`}
      >
        <table
          className="class-sheet w-full table-fixed border-separate border-spacing-0 text-sm"
          style={{ minWidth }}
        >
          <caption className="sr-only">{t("classReport.tableLabel")}</caption>
          <colgroup>
            <col style={{ width: numberWidth }} />
            <col style={{ width: nameWidth }} />
            {sheet.columns.map((column) => (
              <col key={column.id} />
            ))}
          </colgroup>
          <thead
            className={scrolls ? undefined : "sticky z-20"}
            style={scrolls ? undefined : headTop}
          >
            {spans.length ? (
              <tr>
                <th
                  colSpan={2}
                  className={`${pinHead} left-0 border-border bg-card ${pinnedEdge}`}
                  aria-hidden="true"
                />
                {spans.map((item) => (
                  <th
                    key={item.key}
                    colSpan={item.span}
                    scope="colgroup"
                    className={`border-b border-l border-border px-1 py-1.5 text-center text-xs font-medium italic text-muted-foreground ${item.group ? "bg-muted" : "bg-card"}`}
                  >
                    {item.group}
                  </th>
                ))}
              </tr>
            ) : null}
            <tr>
              <th
                scope="col"
                className={`${pinHead} left-0 border-b border-border bg-muted px-2 py-2 text-left text-xs font-semibold`}
              >
                {t("classReport.number")}
              </th>
              <th
                scope="col"
                className={`${pinHead} ${nameLeft} border-b border-border bg-muted px-2 py-2 text-left text-xs font-semibold ${pinnedEdge}`}
              >
                {t("grid.student")}
              </th>
              {sheet.columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  className="border-b border-l border-border bg-muted px-1 py-2 text-center align-bottom text-xs font-semibold break-words"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.students.map((student, index) => (
              <tr
                key={student.student_id}
                tabIndex={0}
                aria-label={student.full_name}
                onKeyDown={moveMark}
                className={`class-sheet-row cursor-pointer outline-none ${index % 2 ? "bg-muted" : "bg-card"}`}
              >
                {/* The pinned cells take the row's shade so the scrolling grades pass under them. */}
                <td
                  className={`tabular ${pinCell} left-0 border-t border-border bg-inherit px-2 py-2 text-muted-foreground`}
                >
                  {student.school_number ?? "—"}
                </td>
                <td
                  className={`${pinCell} ${nameLeft} truncate border-t border-border bg-inherit px-2 py-2 font-semibold ${pinnedEdge}`}
                >
                  {student.full_name}
                </td>
                {student.values.map((value, position) => (
                  <td
                    key={sheet.columns[position]?.id ?? position}
                    className="tabular border-t border-l border-border/60 px-1 py-2 text-center"
                  >
                    {value ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ClassSheetScaleLegend columns={sheet.columns} />
    </div>
  );
}
