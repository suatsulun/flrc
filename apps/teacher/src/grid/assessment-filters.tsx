import type { GridColumnOut } from "@flrc/api-client";
import { useTranslation } from "react-i18next";
import { assessmentOptions, type AssessmentFilter } from "./assessment-filter";

export function AssessmentFilters({
  columns,
  value,
  onChange,
  compact = false,
}: {
  columns: GridColumnOut[];
  value: AssessmentFilter;
  onChange: (value: AssessmentFilter) => void;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const options = assessmentOptions(columns);
  if (options.length < 2) return null;
  return (
    <div role="group" aria-label={t("grid.assessmentCategories")} className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          aria-pressed={value === option.id}
          onClick={() => onChange(option.id)}
          className={[
            "inline-flex max-w-full items-center gap-2 rounded-lg border text-left text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
            compact ? "px-2 py-1.5" : "px-3 py-2",
            value === option.id
              ? "border-primary bg-primary text-primary-foreground"
              : "border-border bg-background text-foreground hover:bg-accent",
          ].join(" ")}
        >
          <span>
            {option.id === "all"
              ? t("grid.allAssessments")
              : option.id === "notes"
                ? t("grid.teacherNotes")
                : option.label}
          </span>
          <span className="tabular text-xs opacity-70">{option.count}</span>
        </button>
      ))}
    </div>
  );
}
