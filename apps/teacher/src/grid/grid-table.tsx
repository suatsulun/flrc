import { TableCaption } from "@flrc/ui/components/table";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { tableFeatures, useTable, type ColumnDef } from "@tanstack/react-table";
import { useTranslation } from "react-i18next";
import { ChevronLeftIcon, ChevronRightIcon, TriangleAlertIcon } from "lucide-react";
import type { GridOut, GridRowOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { SCALE3_FACES } from "@flrc/ui/grid/cells";
import { GradeCell } from "./grade-cell";
import { useGridKeyboard } from "./use-grid-keyboard";
import { assessmentOptions, filterAssessments, type AssessmentFilter } from "./assessment-filter";
import { AssessmentFilters } from "./assessment-filters";
import { BulkRatings } from "./bulk-ratings";
import "./english-grid.css";

const gridTableFeatures = tableFeatures({});
type GridColumnDef = ColumnDef<typeof gridTableFeatures, GridRowOut, unknown>;

export const GridTable = memo(function GridTable({
  data,
  readOnly,
}: {
  data: GridOut;
  readOnly: boolean;
}) {
  const { t } = useTranslation();
  const navigation = useGridKeyboard();
  const surface = useRef<HTMLDivElement>(null);
  const [surfaceWidth, setSurfaceWidth] = useState(0);
  const [selection, setSelection] = useState<{ group: AssessmentFilter; page: number }>({
    group: "all",
    page: 0,
  });

  useEffect(() => {
    const element = surface.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setSurfaceWidth(entry.contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const groups = useMemo(() => assessmentOptions(data.columns), [data.columns]);
  const selectedGroup = groups.some((group) => group.id === selection.group)
    ? selection.group
    : "all";
  const filtered = useMemo(
    () => filterAssessments(data.columns, selectedGroup),
    [data.columns, selectedGroup],
  );
  const scoreCount = filtered.filter((column) => column.value_type === "score").length;
  const noteCount = filtered.filter((column) => column.value_type === "text").length;
  // The final comment column provides room above it for the last slanted header.
  // Smaller screens retain the readable, paged grid and the phone stepper.
  const englishOverview =
    data.meta.subject === "english" &&
    data.meta.grade_level >= 5 &&
    scoreCount > 0 &&
    noteCount > 0 &&
    scoreCount + noteCount === filtered.length &&
    surfaceWidth >= 154 + 184 * noteCount + 60 * scoreCount;
  // Keep student controls in 184px and reserve 180px per sentence. This fits
  // four assessments at 1280px and five at 1366px with the sidebar open.
  const pageSize = englishOverview
    ? filtered.length
    : Math.min(5, Math.max(1, Math.floor((surfaceWidth - 184) / 180)));
  const showScaleFaces = data.meta.subject === "english" && data.meta.grade_level <= 4;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const page = Math.min(selection.page, pageCount - 1);
  const start = page * pageSize;
  const visible = useMemo(
    () =>
      englishOverview
        ? [
            ...filtered.filter((column) => column.value_type === "score"),
            ...filtered.filter((column) => column.value_type === "text"),
          ]
        : filtered.slice(start, start + pageSize),
    [filtered, start, pageSize, englishOverview],
  );

  const columns = useMemo<GridColumnDef[]>(() => {
    return [
      {
        id: "student",
        header: t("grid.student"),
        cell: (context) => (
          <div className={`min-w-0 py-1 text-left ${englishOverview ? "text-xs" : ""}`}>
            <span
              className="block font-medium leading-relaxed"
              title={context.row.original.full_name}
            >
              {context.row.original.full_name}
            </span>
            <span className="tabular mt-0.5 block text-xs text-muted-foreground">
              {context.row.original.school_number ?? "—"}
            </span>
            {!englishOverview ? (
              <div className="mt-2">
                <BulkRatings data={data} row={context.row.original} readOnly={readOnly} />
              </div>
            ) : null}
          </div>
        ),
      },
      ...visible.map<GridColumnDef>((column, index) => ({
        id: String(column.id),
        header: () =>
          englishOverview && column.value_type === "score" ? (
            <>
              <span className="english-slanted-border" aria-hidden="true" />
              <span
                className="english-slanted-label"
                title={`${column.label} · ${t(`roles.${column.owner_role}`)} · ${column.owner_name ?? t("grid.unassignedOwner")}`}
              >
                <span data-testid="assessment-heading">{column.label}</span>
              </span>
              <span
                className={`english-owner ${column.owned_by_you ? "" : "text-warning"}`}
                title={t("grid.ownedBy", { name: column.owner_name ?? t("grid.unassignedOwner") })}
              >
                {!column.owned_by_you ? (
                  <TriangleAlertIcon className="size-3" aria-hidden="true" />
                ) : null}
                <span className="sr-only">
                  {t("grid.ownedBy", { name: column.owner_name ?? t("grid.unassignedOwner") })}
                </span>
              </span>
            </>
          ) : (
            <div className={englishOverview ? "english-note-heading space-y-1" : "space-y-2"}>
              {column.group ? (
                <span className="block text-xs font-medium text-muted-foreground">
                  {column.group}
                </span>
              ) : null}
              <span
                data-testid="assessment-heading"
                className="block text-sm font-semibold leading-relaxed text-foreground"
              >
                {column.label}
              </span>
              {!column.owned_by_you ? (
                <span className="flex items-start gap-1.5 text-xs font-normal text-warning">
                  <TriangleAlertIcon className="mt-0.5 size-3.5 shrink-0" />
                  {t("grid.ownedBy", { name: column.owner_name ?? t("grid.unassignedOwner") })}
                </span>
              ) : null}
            </div>
          ),
        cell: (context) => (
          <GradeCell
            column={column}
            row={context.row.original}
            rowIndex={context.row.index}
            columnIndex={index + 1}
            readOnly={readOnly}
            navigation={navigation}
            showScaleFaces={showScaleFaces}
            fit
          />
        ),
      })),
    ];
  }, [visible, navigation, readOnly, t, data, showScaleFaces, englishOverview]);

  const table = useTable({ features: gridTableFeatures, data: data.rows, columns });
  const paging = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p role="status" className="text-sm font-medium text-foreground">
        {t("grid.assessmentRange", {
          start: filtered.length ? start + 1 : 0,
          end: Math.min(start + pageSize, filtered.length),
          total: filtered.length,
        })}
      </p>
      {pageCount > 1 ? (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 0}
            onClick={() => setSelection({ group: selectedGroup, page: page - 1 })}
          >
            <ChevronLeftIcon />
            {t("grid.previousAssessments")}
          </Button>
          <span className="tabular text-xs text-muted-foreground">
            {page + 1} / {pageCount}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page === pageCount - 1}
            onClick={() => setSelection({ group: selectedGroup, page: page + 1 })}
          >
            {t("grid.nextAssessments")}
            <ChevronRightIcon />
          </Button>
        </div>
      ) : null}
    </div>
  );

  return (
    <div
      ref={surface}
      data-testid="grade-grid-surface"
      aria-label={t("grid.tableLabel")}
      className={`w-full min-w-0 overflow-visible rounded-xl border border-border bg-card shadow-card ${englishOverview ? "english-overview" : ""}`}
      data-layout={englishOverview ? "english-overview" : "paged"}
    >
      <div
        className={
          englishOverview
            ? "space-y-2 border-b border-border p-2"
            : "space-y-3 border-b border-border p-3"
        }
      >
        <AssessmentFilters
          compact={!englishOverview}
          columns={data.columns}
          value={selectedGroup}
          onChange={(group) => setSelection({ group, page: 0 })}
        />
        {englishOverview ? null : paging}
        {visible.some((column) => column.value_type === "scale3") ? (
          <div
            className="flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-3 text-xs text-muted-foreground"
            aria-label={t("classWorkspace.typeScale")}
          >
            {([1, 2, 3] as const).map((level) => (
              <span key={level}>
                <span className="font-semibold text-foreground">
                  {level}{" "}
                  {showScaleFaces ? <span aria-hidden="true">{SCALE3_FACES[level]}</span> : null}
                </span>{" "}
                · {t(`grid.scaleLevels.${level}`)}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      {filtered.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">{t("grid.noTeacherNotes")}</p>
      ) : (
        <table className="w-full table-fixed border-separate border-spacing-0 text-sm">
          <TableCaption>{t("grid.tableLabel")}</TableCaption>
          <colgroup>
            <col style={{ width: englishOverview ? 154 : pageSize === 1 ? "36%" : 184 }} />
            {visible.map((column) => (
              <col
                key={column.id}
                style={englishOverview && column.value_type === "text" ? { width: 184 } : undefined}
              />
            ))}
          </colgroup>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    scope="col"
                    className={
                      englishOverview
                        ? `sticky z-20 border-b border-border text-left text-sm font-semibold text-foreground ${header.column.id === "student" ? "english-student-heading" : visible.find((column) => String(column.id) === header.column.id)?.value_type === "score" ? "english-score-heading" : "english-comment-heading"}`
                        : "sticky z-20 border-b border-border bg-muted px-2 py-3 text-left align-top text-sm font-semibold break-words text-foreground"
                    }
                    style={{ top: "var(--app-shell-header-height, 3.5rem)" }}
                  >
                    <table.FlexRender header={header} />
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="group transition-colors even:bg-muted/25 hover:bg-accent/40 focus-within:bg-accent/55"
              >
                {row.getAllCells().map((cell) => (
                  <td
                    key={cell.id}
                    data-testid={
                      cell.column.id === "student"
                        ? undefined
                        : `cell-${row.original.student_id}-${cell.column.id}`
                    }
                    className={
                      englishOverview
                        ? "min-w-0 border-b border-r border-border/60 px-0.5 py-1 break-words first:px-2 last:px-2"
                        : "min-w-0 border-b border-border/60 px-2 py-2 break-words"
                    }
                  >
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {pageCount > 1 ? <div className="p-4">{paging}</div> : null}
    </div>
  );
});
