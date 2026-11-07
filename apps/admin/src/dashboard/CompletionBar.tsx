import { useTranslation } from "react-i18next";
import { formatPercent } from "./format";

/**
 * A completion bar with its percentage. `null` means nothing is expected yet: a full green bar
 * there would read as a false all-clear, so a dash is shown instead.
 */
export function CompletionBar({ percent }: { percent: number | null }) {
  const { i18n } = useTranslation();
  if (percent === null) return <span className="text-muted-foreground">—</span>;
  const label = formatPercent(percent, i18n.language);
  return (
    <span className="flex items-center gap-2.5">
      <span
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={label}
      >
        <span
          className={`block h-full rounded-full ${percent >= 99.95 ? "bg-success" : "bg-primary"}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </span>
      <span className="tabular w-14 shrink-0 text-right text-xs text-muted-foreground">
        {label}
      </span>
    </span>
  );
}
