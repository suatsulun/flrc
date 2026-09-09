import { useTranslation } from "react-i18next";
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

/**
 * Temporary-grant prompt. Not currently wired into the grid: saving outside your
 * assignment goes through `OwnershipWarningDialog` instead. Kept, and kept on the
 * design system, for when the request-access flow is turned back on.
 */
export function GrantDialog({
  column,
  onAccept,
  onClose,
}: {
  column: GridColumnOut | null;
  onAccept: (role: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={column !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-warning">{t("grid.grantTitle")}</DialogTitle>
          <DialogDescription>
            {column?.owner_name
              ? t("grid.grantBody", { name: column.owner_name, label: column.label })
              : t("grid.noOwner")}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("grid.cancel")}
          </Button>
          <Button
            className="bg-warning text-warning-foreground hover:bg-warning/90"
            disabled={!column?.owner_name}
            onClick={() => column && onAccept(column.owner_role)}
          >
            {t("grid.grantAccept")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
