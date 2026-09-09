import { useTranslation } from "react-i18next";
import { TriangleAlertIcon } from "lucide-react";
import type { GridColumnOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";

export function OwnershipWarningDialog({
  columns,
  isAdmin,
  pending,
  onAccept,
  onClose,
}: {
  columns: GridColumnOut[];
  isAdmin: boolean;
  pending: boolean;
  onAccept: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={columns.length > 0} onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent className="sm:max-w-lg" showCloseButton={!pending}>
        <DialogHeader>
          <div className="mb-1 grid size-9 place-items-center rounded-lg bg-warning-surface text-warning">
            <TriangleAlertIcon className="size-4.5" />
          </div>
          <DialogTitle className="text-base">{t("grid.ownershipWarningTitle")}</DialogTitle>
          <DialogDescription>
            {isAdmin ? t("grid.adminOwnershipWarningBody") : t("grid.ownershipWarningBody")}
          </DialogDescription>
        </DialogHeader>

        <ul className="divide-y divide-border rounded-lg border border-border">
          {columns.map((column) => (
            <li
              className="flex items-center justify-between gap-4 px-3 py-2 text-sm"
              key={column.id}
            >
              <span className="font-medium">{column.label}</span>
              <span className="text-right text-muted-foreground">
                {column.owner_name ?? t("grid.unassignedOwner")}
              </span>
            </li>
          ))}
        </ul>

        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={onClose}>
            {t("grid.cancel")}
          </Button>
          {/* Stable hook for the two-writer collision e2e test, so the crown-jewel
              check does not break every time this copy is reworded. */}
          <Button
            data-testid="confirm-ownership"
            pending={pending}
            pendingLabel={t("grid.saving")}
            onClick={onAccept}
          >
            {isAdmin ? t("grid.adminSave") : t("grid.confirmAndSave")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
