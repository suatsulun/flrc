import { cn } from "#lib/utils";

export type SegmentedOption<T extends string | number> = {
  value: T;
  label: string;
  /** Full label for assistive tech when `label` is an abbreviation. */
  title?: string;
};

/**
 * Compact single-choice control — language, view mode, semester.
 *
 * Preferred over a dropdown when there are two to five options: one click
 * instead of two, and the alternatives stay visible.
 */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  ariaLabel,
  size = "default",
  className,
}: {
  options: ReadonlyArray<SegmentedOption<T>>;
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: "sm" | "default";
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex max-w-full flex-wrap items-center gap-0.5 rounded-lg border border-border bg-muted/60 p-0.5",
        className,
      )}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            role="radio"
            aria-checked={active}
            title={option.title ?? option.label}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-[0.3rem] font-medium transition-colors",
              "focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              size === "sm" ? "px-2 py-1 text-[0.6875rem]" : "px-2.5 py-1.5 text-xs",
              active
                ? "bg-card text-foreground shadow-card"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
