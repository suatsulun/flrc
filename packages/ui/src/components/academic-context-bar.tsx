import { CalendarDaysIcon, ChevronLeftIcon, ChevronRightIcon, LockIcon } from "lucide-react";

import { Badge } from "#components/badge";
import { Button } from "#components/button";
import { NativeSelect } from "#components/native-select";
import { Segmented } from "#components/segmented";

export type AcademicContextYear = {
  id: number;
  label: string;
  status: string;
  semesters: Array<{ id: number; number: number; status: string }>;
};

/**
 * Shared year/term navigation for both workspaces. Years remain visible in a
 * single linear control so archives never feel like a separate product.
 */
export function AcademicContextBar({
  years,
  yearId,
  semesterNumber,
  onYearChange,
  onSemesterChange,
  labels,
}: {
  years: AcademicContextYear[];
  yearId: number;
  semesterNumber: number;
  onYearChange: (yearId: number) => void;
  onSemesterChange: (semester: number) => void;
  labels: {
    year: string;
    previousYear: string;
    nextYear: string;
    semester: string;
    semesterShort: (number: number) => string;
    active: string;
    setup: string;
    archived: string;
    locked: string;
  };
}) {
  const ordered = [...years].sort((left, right) => left.label.localeCompare(right.label));
  const index = ordered.findIndex((year) => year.id === yearId);
  const current = ordered[index];
  const semester = current?.semesters.find((item) => item.number === semesterNumber);
  const statusLabel = current ? labels[current.status as "active" | "setup" | "archived"] : "";

  return (
    <section className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-2.5 py-2 shadow-card">
      <span className="ml-1 hidden items-center gap-2 text-xs font-semibold text-muted-foreground sm:flex">
        <CalendarDaysIcon className="size-4" />
        {labels.year}
      </span>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={labels.previousYear}
        disabled={index <= 0}
        onClick={() => ordered[index - 1] && onYearChange(ordered[index - 1].id)}
      >
        <ChevronLeftIcon />
      </Button>
      <NativeSelect
        className="w-36 font-semibold tabular"
        aria-label={labels.year}
        value={yearId}
        onChange={(event) => onYearChange(Number(event.target.value))}
      >
        {ordered.map((year) => (
          <option key={year.id} value={year.id}>
            {year.label}
          </option>
        ))}
      </NativeSelect>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={labels.nextYear}
        disabled={index < 0 || index >= ordered.length - 1}
        onClick={() => ordered[index + 1] && onYearChange(ordered[index + 1].id)}
      >
        <ChevronRightIcon />
      </Button>

      {current ? (
        <Badge tone={current.status === "active" ? "success" : "neutral"}>{statusLabel}</Badge>
      ) : null}

      <span className="mx-1 hidden h-6 w-px bg-border sm:block" />
      <Segmented
        ariaLabel={labels.semester}
        value={semesterNumber}
        onChange={onSemesterChange}
        options={(current?.semesters ?? []).map((item) => ({
          value: item.number,
          label: labels.semesterShort(item.number),
        }))}
        size="sm"
      />
      {semester?.status === "locked" ? (
        <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <LockIcon className="size-3.5" />
          {labels.locked}
        </span>
      ) : null}
    </section>
  );
}
