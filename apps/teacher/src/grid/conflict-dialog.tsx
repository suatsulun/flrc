import { useTranslation } from "react-i18next";
import { GitCompareArrowsIcon } from "lucide-react";
import type { ConflictOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";

const show = (value: unknown) =>
  value === null || value === undefined || value === "" ? "—" : String(value);

export function ConflictDialog({
  conflicts,
  pending,
  onAccept,
  onCancel,
}: {
  conflicts: ConflictOut[];
  pending: boolean;
  onAccept: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={conflicts.length > 0} onOpenChange={(open) => !open && !pending && onCancel()}>
      <DialogContent className="sm:max-w-lg" showCloseButton={!pending}>
        <DialogHeader>
          <div className="mb-1 grid size-9 place-items-center rounded-lg bg-warning-surface text-warning">
            <GitCompareArrowsIcon className="size-4.5" />
          </div>
          <DialogTitle className="text-base">{t("grid.conflictTitle")}</DialogTitle>
          <DialogDescription>{t("grid.conflictBody")}</DialogDescription>
        </DialogHeader>

        <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border">
          {conflicts.map((conflict) => (
            <li
              className="px-3 py-2.5 text-sm"
              key={`${conflict.student_id}:${conflict.column_id}`}
            >
              <p className="font-medium">
                {conflict.student_name}
                <span className="font-normal text-muted-foreground">
                  {" "}
                  · {conflict.column_label}
                </span>
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                <span className="text-muted-foreground">
                  {t("grid.yours")}{" "}
                  <b className="tabular text-foreground">{show(conflict.your_value)}</b>
                </span>
                <span className="text-muted-foreground">
                  {t("grid.current")}{" "}
                  <b className="tabular text-foreground">{show(conflict.current_value)}</b>
                </span>
                {conflict.updated_by ? (
                  <span className="text-muted-foreground">({conflict.updated_by})</span>
                ) : null}
              </p>
            </li>
          ))}
        </ul>

        <DialogFooter>
          {/* Stable hooks for the two-writer collision e2e test. */}
          <Button
            data-testid="keep-database"
            variant="outline"
            disabled={pending}
            onClick={onCancel}
          >
            {t("grid.keepDb")}
          </Button>
          <Button
            data-testid="confirm-overwrite"
            className="bg-warning text-warning-foreground hover:bg-warning/90"
            pending={pending}
            pendingLabel={t("grid.saving")}
            onClick={onAccept}
          >
            {t("grid.overwrite")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
