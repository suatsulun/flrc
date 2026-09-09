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
  const [pageSize, setPageSize] = useState(1);
  const [selection, setSelection] = useState<{ group: string | null; page: number }>({
    group: null,
    page: 0,
  });

  useEffect(() => {
    const element = surface.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      // Reserve space for student names, then at least 240px per assessment.
      setPageSize(Math.min(3, Math.max(1, Math.floor((entry.contentRect.width - 224) / 240))));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const column of data.columns) {
      if (column.group) counts.set(column.group, (counts.get(column.group) ?? 0) + 1);
    }
    return [...counts].map(([label, count]) => ({ label, count }));
  }, [data.columns]);
  const selectedGroup = groups.some((group) => group.label === selection.group)
    ? selection.group
    : null;
  const filtered = useMemo(
    () => data.columns.filter((column) => !selectedGroup || column.group === selectedGroup),
    [data.columns, selectedGroup],
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const page = Math.min(selection.page, pageCount - 1);
  const start = page * pageSize;
  const visible = useMemo(
    () => filtered.slice(start, start + pageSize),
    [filtered, start, pageSize],
  );

  const columns = useMemo<GridColumnDef[]>(() => {
    return [
      {
        id: "student",
        header: t("grid.student"),
        cell: (context) => (
          <div className="min-w-0 py-1 text-left">
            <span className="block font-medium leading-relaxed">
              {context.row.original.full_name}
            </span>
            <span className="tabular mt-0.5 block text-xs text-muted-foreground">
              {context.row.original.school_number ?? "—"}
            </span>
          </div>
        ),
      },
      ...visible.map<GridColumnDef>((column, index) => ({
        id: String(column.id),
        header: () => (
          <div className="space-y-2">
            {column.group ? (
              <span className="block text-xs font-medium text-muted-foreground">
                {column.group}
              </span>
            ) : null}
            <span
              data-testid="assessment-heading"
              className="block text-sm font-semibold leading-relaxed text-foreground lg:text-base"
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
            fit
          />
        ),
      })),
    ];
  }, [visible, navigation, readOnly, t]);

  const table = useTable({ features: gridTableFeatures, data: data.rows, columns });
  const paging = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p role="status" className="text-sm font-medium text-foreground">
        {t("grid.assessmentRange", {
          start: start + 1,
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
      className="w-full min-w-0 overflow-visible rounded-xl border border-border bg-card shadow-card"
    >
      <div className="space-y-4 border-b border-border p-4">
        <div>
          <p className="font-semibold">{t("grid.assessmentFocus")}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t("grid.assessmentFocusHint")}</p>
        </div>
        {groups.length > 0 ? (
          <div
            role="group"
            aria-label={t("grid.assessmentCategories")}
            className="flex flex-wrap gap-2"
          >
            {[{ label: null, count: data.columns.length }, ...groups].map((group) => (
              <button
                key={group.label ?? "all"}
                type="button"
                aria-pressed={selectedGroup === group.label}
                onClick={() => setSelection({ group: group.label, page: 0 })}
                className={[
                  "inline-flex max-w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                  selectedGroup === group.label
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background text-foreground hover:bg-accent",
                ].join(" ")}
              >
                <span>{group.label ?? t("grid.allAssessments")}</span>
                <span className="tabular text-xs opacity-70">{group.count}</span>
              </button>
            ))}
          </div>
        ) : null}
        {paging}
        {visible.some((column) => column.value_type === "scale3") ? (
          <div
            className="flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-3 text-xs text-muted-foreground"
            aria-label={t("classWorkspace.typeScale")}
          >
            {([1, 2, 3] as const).map((level) => (
              <span key={level}>
                <span className="font-semibold text-foreground">
                  {level} {SCALE3_FACES[level]}
                </span>{" "}
                · {t(`grid.scaleLevels.${level}`)}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <table className="w-full table-fixed border-separate border-spacing-0 text-sm">
        <TableCaption>{t("grid.tableLabel")}</TableCaption>
        <colgroup>
          <col style={{ width: pageSize === 1 ? "36%" : "28%" }} />
          {visible.map((column) => (
            <col key={column.id} />
          ))}
        </colgroup>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  scope="col"
                  className="sticky z-20 border-b border-border bg-muted px-3 py-4 text-left align-top text-sm font-semibold break-words text-foreground"
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
                  className="min-w-0 border-b border-border/60 px-3 py-2 break-words"
                >
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pageCount > 1 ? <div className="p-4">{paging}</div> : null}
    </div>
  );
});
