import { useTranslation } from "react-i18next";
import { GripVerticalIcon, Trash2Icon } from "lucide-react";
import type { PreviewClass, PreviewRow } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { NativeSelect } from "@flrc/ui/components/native-select";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
  TableScroll,
} from "@flrc/ui/components/table";

export function ImportRoster({
  rows,
  classes,
  busy,
  loading,
  refreshing,
  onMove,
  onRemove,
  onLanguage,
  onDrag,
  onDragEnd,
}: {
  rows: PreviewRow[];
  classes: PreviewClass[];
  busy: boolean;
  loading: boolean;
  refreshing: boolean;
  onMove: (row: PreviewRow, destination: string) => void;
  onRemove: (row: PreviewRow) => void;
  onLanguage: (row: PreviewRow, language: "german" | "french" | null) => void;
  onDrag: (row: PreviewRow) => void;
  onDragEnd: () => void;
}) {
  const { t } = useTranslation();
  return (
    <TableScroll
      data-testid="import-roster-surface"
      aria-label={t("import.tableLabel")}
      className="max-h-none overflow-visible"
    >
      <Table
        className={`w-full table-fixed [&_td]:whitespace-normal [&_th]:whitespace-normal ${refreshing ? "opacity-60" : ""}`}
      >
        <TableCaption>{t("import.tableLabel")}</TableCaption>
        <TableHead>
          <tr>
            <TableHeader className="w-10">
              <span className="sr-only">{t("import.moveStudent")}</span>
            </TableHeader>
            <TableHeader className="hidden w-20 sm:table-cell">
              {t("students.schoolNumber")}
            </TableHeader>
            <TableHeader>{t("students.fullName")}</TableHeader>
            <TableHeader className="w-28">{t("classes.title")}</TableHeader>
            <TableHeader className="hidden w-40 xl:table-cell">
              {t("import.filterLanguage")}
            </TableHeader>
            <TableHeader className="hidden w-28 sm:table-cell xl:w-36">
              {t("import.actions")}
            </TableHeader>
            <TableHeader className="w-12">
              <span className="sr-only">{t("import.removeStudent")}</span>
            </TableHeader>
          </tr>
        </TableHead>
        <TableBody>
          {!rows.length ? (
            <TableEmpty colSpan={7}>
              {loading ? t("import.previewing") : t("import.noMatches")}
            </TableEmpty>
          ) : (
            rows.map((item) => {
              const { row, actions } = item;
              const currentClass = `${row.grade_level}/${row.section}`;
              return (
                <TableRow
                  key={row.school_number}
                  data-testid="import-student-row"
                  data-school-number={row.school_number}
                  className={actions.includes("class_changed") ? "bg-accent/35" : undefined}
                >
                  <TableCell>
                    <button
                      type="button"
                      draggable={!busy}
                      disabled={busy}
                      aria-label={t("import.dragStudent", { name: row.full_name })}
                      className="rounded p-1 text-muted-foreground outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring enabled:cursor-grab active:cursor-grabbing disabled:opacity-40"
                      onClick={(event) =>
                        event.currentTarget
                          .closest("tr")
                          ?.querySelector<HTMLSelectElement>("select[data-class-selector]")
                          ?.focus()
                      }
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", String(row.school_number));
                        onDrag(item);
                      }}
                      onDragEnd={onDragEnd}
                    >
                      <GripVerticalIcon className="size-4" />
                    </button>
                  </TableCell>
                  <TableCell className="tabular hidden text-muted-foreground sm:table-cell">
                    {row.school_number}
                  </TableCell>
                  <TableCell>
                    <span className="tabular mb-1 block text-xs text-muted-foreground sm:hidden">
                      {row.school_number}
                    </span>
                    <span className="block font-medium">{row.full_name}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {row.row_number === 0
                        ? t("import.rowActions.manual_added")
                        : t("import.sourceRow", { sheet: row.sheet, row: row.row_number })}
                    </span>
                    <LanguageSelect
                      item={item}
                      busy={busy}
                      onLanguage={onLanguage}
                      className="mt-2 w-full max-w-40 xl:hidden"
                    />
                    <span className="mt-1 flex flex-wrap gap-1 sm:hidden">
                      {actions.map((action) => (
                        <Badge
                          key={action}
                          className="max-w-full whitespace-normal"
                          tone={action === "class_changed" ? "info" : "outline"}
                        >
                          {t(`import.rowActions.${action}`)}
                        </Badge>
                      ))}
                    </span>
                  </TableCell>
                  <TableCell>
                    <NativeSelect
                      data-class-selector
                      className="w-full"
                      aria-label={t("import.moveStudentLabel", { name: row.full_name })}
                      value={currentClass}
                      disabled={busy}
                      onChange={(event) => onMove(item, event.target.value)}
                    >
                      {classes.map((c) => (
                        <option
                          key={`${c.grade_level}/${c.section}`}
                          value={`${c.grade_level}/${c.section}`}
                        >
                          {c.grade_level}/{c.section}
                        </option>
                      ))}
                    </NativeSelect>
                    {item.original_class !== currentClass ? (
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {t("import.originalClass", { className: item.original_class })}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="hidden text-xs xl:table-cell">
                    <LanguageSelect
                      item={item}
                      busy={busy}
                      onLanguage={onLanguage}
                      className="w-full"
                    />
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <span className="flex flex-wrap gap-1">
                      {actions.map((action) => (
                        <Badge
                          key={action}
                          className="max-w-full whitespace-normal"
                          tone={action === "class_changed" ? "info" : "outline"}
                        >
                          {t(`import.rowActions.${action}`)}
                        </Badge>
                      ))}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      disabled={busy}
                      aria-label={t("import.removeStudentLabel", { name: row.full_name })}
                      title={t("import.removeStudent")}
                      onClick={() => onRemove(item)}
                    >
                      <Trash2Icon className="size-4 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </TableScroll>
  );
}

function LanguageSelect({
  item,
  busy,
  onLanguage,
  className,
}: {
  item: PreviewRow;
  busy: boolean;
  onLanguage: (row: PreviewRow, language: "german" | "french" | null) => void;
  className: string;
}) {
  const { t } = useTranslation();
  return (
    <div className={`${className} [&>span]:w-full`}>
      <NativeSelect
        className="w-full"
        aria-label={t("import.studentLanguage", { name: item.row.full_name })}
        title={item.row.language ? t(`subjects.${item.row.language}`) : t("import.noLanguage")}
        value={item.row.language ?? ""}
        disabled={busy}
        onChange={(e) => onLanguage(item, (e.target.value || null) as "german" | "french" | null)}
      >
        <option value="">{t("import.noLanguageShort")}</option>
        <option value="german" disabled={item.row.grade_level < 4}>
          {t("subjects.german")}
        </option>
        <option value="french" disabled={item.row.grade_level < 4}>
          {t("subjects.french")}
        </option>
      </NativeSelect>
    </div>
  );
}
