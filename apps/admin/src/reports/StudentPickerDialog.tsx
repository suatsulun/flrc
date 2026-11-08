import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SearchIcon } from "lucide-react";
import type { RosterClass } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Checkbox } from "@flrc/ui/components/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";
import { Input } from "@flrc/ui/components/input";
import { Segmented } from "@flrc/ui/components/segmented";
import { cn } from "@flrc/ui/lib/utils";
import { planDelivery, reportFormatOptions, type ReportFormat } from "./report-requests";

const INDETERMINATE =
  "data-indeterminate:border-primary data-indeterminate:bg-primary/45 data-indeterminate:text-primary-foreground";

/**
 * Tick students across every class of one card kind. The selection survives switching classes
 * and searching; one student or one class prints at once, more becomes a background job.
 */
export function StudentPickerDialog({
  open,
  onOpenChange,
  title,
  roster,
  demo,
  pending,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  roster: RosterClass[];
  demo: boolean;
  pending: boolean;
  onSubmit: (selected: ReadonlySet<number>, format: ReportFormat) => void;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [activeClassId, setActiveClassId] = useState<number>();
  const [search, setSearch] = useState("");
  const [format, setFormat] = useState<ReportFormat>("combined");

  const activeClass = roster.find((item) => item.id === activeClassId) ?? roster[0];
  const everyone = roster.flatMap((item) => item.students);
  // Ids from another semester or card kind never leave the dialog.
  const current = new Set(everyone.filter((student) => selected.has(student.id)).map((s) => s.id));
  const query = search.trim().toLocaleLowerCase("tr");
  const rows = query
    ? roster.flatMap((item) =>
        item.students
          .filter((student) =>
            `${student.school_number ?? ""} ${student.full_name}`
              .toLocaleLowerCase("tr")
              .includes(query),
          )
          .map((student) => ({ student, className: item.name })),
      )
    : (activeClass?.students ?? []).map((student) => ({ student, className: null }));
  const plan = current.size > 0 ? planDelivery(roster, current, format) : null;
  const needsJob = plan !== null && "job" in plan;

  const toggle = (ids: number[], on: boolean) => {
    const next = new Set(current);
    for (const id of ids) {
      if (on) next.add(id);
      else next.delete(id);
    }
    setSelected(next);
  };
  const allChecked = everyone.length > 0 && current.size === everyone.length;

  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent
        showCloseButton={!pending}
        className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_auto_minmax(0,1fr)_auto_auto] overflow-hidden sm:max-w-3xl"
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{t("reports.picker.description")}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-0 flex-1 basis-56">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              className="pl-9"
              aria-label={t("reports.picker.search")}
              placeholder={t("reports.picker.search")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <label className="flex items-center gap-2.5 text-sm font-medium">
            <Checkbox
              aria-label={t("reports.picker.everyone", { count: everyone.length })}
              checked={allChecked}
              indeterminate={current.size > 0 && !allChecked}
              className={INDETERMINATE}
              onCheckedChange={(on) =>
                toggle(
                  everyone.map((student) => student.id),
                  on,
                )
              }
            />
            {t("reports.picker.everyone", { count: everyone.length })}
          </label>
        </div>

        <div className="grid min-h-0 gap-3 sm:grid-cols-[14rem_minmax(0,1fr)]">
          <ul
            aria-label={t("reports.picker.classes")}
            className="max-h-36 min-h-0 overflow-y-auto rounded-xl border border-border sm:max-h-none"
          >
            {roster.map((item) => {
              const ids = item.students.map((student) => student.id);
              const ticked = ids.filter((id) => current.has(id)).length;
              const isActive = !query && item.id === activeClass?.id;
              return (
                <li
                  key={item.id}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-1.5",
                    isActive && "bg-accent text-accent-foreground",
                  )}
                >
                  <Checkbox
                    aria-label={t("reports.picker.wholeClass", { name: item.name })}
                    checked={ticked === ids.length}
                    indeterminate={ticked > 0 && ticked < ids.length}
                    className={INDETERMINATE}
                    onCheckedChange={(on) => toggle(ids, on)}
                  />
                  <button
                    type="button"
                    aria-current={isActive || undefined}
                    className="min-w-0 flex-1 truncate py-1 text-left text-sm font-medium"
                    onClick={() => {
                      setActiveClassId(item.id);
                      setSearch("");
                    }}
                  >
                    {item.name}
                  </button>
                  <span className="tabular text-xs text-muted-foreground">
                    {ticked}/{ids.length}
                  </span>
                </li>
              );
            })}
          </ul>

          <div className="max-h-[45dvh] min-h-0 overflow-y-auto rounded-xl border border-border sm:max-h-[50dvh]">
            {rows.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                {t("reports.picker.noMatches")}
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {rows.map(({ student, className }) => (
                  <li key={student.id}>
                    <label className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-muted/60">
                      <Checkbox
                        aria-label={student.full_name}
                        checked={current.has(student.id)}
                        onCheckedChange={(on) => toggle([student.id], on)}
                      />
                      <span className="tabular w-14 shrink-0 text-muted-foreground">
                        {student.school_number ?? "—"}
                      </span>
                      <span className="min-w-0 flex-1 truncate">{student.full_name}</span>
                      {className ? (
                        <span className="shrink-0 text-xs text-muted-foreground">{className}</span>
                      ) : null}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="grid gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium" aria-live="polite">
              {t("reports.picker.selected", { count: current.size })}
            </p>
            <Segmented
              ariaLabel={t("reports.formatLabel")}
              options={reportFormatOptions(t)}
              value={format}
              onChange={setFormat}
              size="sm"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {plan === null
              ? t("reports.picker.nothingSelected")
              : needsJob
                ? demo
                  ? t("reports.errors.demoJobs")
                  : t("reports.picker.jobHint")
                : t("reports.picker.directHint")}
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)}>
            {t("forms.cancel")}
          </Button>
          <Button
            pending={pending}
            pendingLabel={t("reports.generatingPdf")}
            disabled={plan === null || (demo && needsJob)}
            onClick={() => onSubmit(current, format)}
          >
            {needsJob ? t("reports.prepare") : t("reports.download")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
