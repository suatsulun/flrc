import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import type { GridColumnOut, GridOut, GridRowOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Card } from "@flrc/ui/components/card";

/**
 * One student at a time — the phone path. Thumbs stay near the bottom controls,
 * and the roster position is always visible so nobody loses their place.
 */
export function StepperView({
  data,
  renderCell,
}: {
  data: GridOut;
  renderCell: (column: GridColumnOut, row: GridRowOut) => ReactNode;
}) {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const row = data.rows[index];
  if (!row) return null;

  const progress = ((index + 1) / data.rows.length) * 100;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-3">
      <Card className="overflow-hidden">
        <div className="px-4 py-3 text-center">
          <p className="font-heading truncate text-base font-semibold tracking-tight">
            {row.full_name}
          </p>
          <p className="tabular mt-0.5 text-xs text-muted-foreground">
            {index + 1} / {data.rows.length}
          </p>
        </div>
        <div className="h-0.5 bg-muted" role="presentation">
          <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
        </div>

        <div className="divide-y divide-border">
          {data.columns.map((column) => (
            <label
              key={column.id}
              className="flex items-center justify-between gap-4 px-4 py-3 text-sm"
            >
              <span className="min-w-0">
                {column.group ? (
                  <span className="block text-[0.6875rem] tracking-wide text-muted-foreground uppercase">
                    {column.group}
                  </span>
                ) : null}
                <span className="block font-medium">{column.label}</span>
                {column.owned_by_you ? null : (
                  <span className="mt-0.5 block text-[0.6875rem] text-warning">
                    {t("grid.ownedBy", {
                      name: column.owner_name ?? t("grid.unassignedOwner"),
                    })}
                  </span>
                )}
              </span>
              {renderCell(column, row)}
            </label>
          ))}
        </div>
      </Card>

      <div className="flex items-center gap-2">
        <Button
          className="flex-1"
          variant="outline"
          disabled={index === 0}
          onClick={() => setIndex(index - 1)}
        >
          <ChevronLeftIcon />
          {t("stepper.prev")}
        </Button>
        <Button
          className="flex-1"
          variant="outline"
          disabled={index === data.rows.length - 1}
          onClick={() => setIndex(index + 1)}
        >
          {t("stepper.next")}
          <ChevronRightIcon />
        </Button>
      </div>
    </div>
  );
}
