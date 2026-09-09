import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";

import { useTheme } from "#hooks/use-theme";
import { cn } from "#lib/utils";
import type { ThemePreference } from "#lib/theme";

const OPTIONS: Array<{ value: ThemePreference; Icon: typeof SunIcon }> = [
  { value: "light", Icon: SunIcon },
  { value: "system", Icon: MonitorIcon },
  { value: "dark", Icon: MoonIcon },
];

/**
 * Three-way theme control: light · follow system · dark.
 *
 * `labels` are passed in so the component stays free of an i18n dependency.
 */
export function ThemeToggle({
  labels,
  className,
}: {
  labels: Record<ThemePreference, string>;
  className?: string;
}) {
  const { preference, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label={labels.system}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg border border-border bg-muted/60 p-0.5",
        className,
      )}
    >
      {OPTIONS.map(({ value, Icon }) => {
        const active = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={labels[value]}
            title={labels[value]}
            onClick={() => setTheme(value)}
            className={cn(
              "grid size-7 place-items-center rounded-[0.3rem] transition-colors",
              "focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              active
                ? "bg-card text-foreground shadow-card"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" />
          </button>
        );
      })}
    </div>
  );
}
