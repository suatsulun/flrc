import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Undo2Icon } from "lucide-react";
import type { AdminActionOut } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { ConfirmDialog } from "@flrc/ui/components/dialog";
import { undoChange } from "../admin/undo-toast";
import { useRefreshQueries } from "../admin/use-refresh-queries";
import { parseUtc } from "../dashboard/format";
import { changeSummary, formatChangeTime } from "./summary";

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Whether a change can still be undone, and for how long; who undid it and when; or that its
 * 7-day window ended. `now` is the list's fetch time, so the text matches the loaded status.
 */
export function ChangeStatusBadge({ action, now }: { action: AdminActionOut; now: number }) {
  const { t, i18n } = useTranslation();
  if (action.status === "undone") {
    return (
      <Badge tone="neutral" className="whitespace-normal">
        {action.undone_by && action.undone_at
          ? t("changes.statuses.undoneBy", {
              name: action.undone_by,
              time: formatChangeTime(action.undone_at, i18n.language),
            })
          : t("changes.statuses.undone")}
      </Badge>
    );
  }
  const daysLeft = Math.ceil((parseUtc(action.expires_at).getTime() - now) / DAY_MS);
  if (action.status === "expired" || daysLeft <= 0) {
    return <Badge tone="neutral">{t("changes.statuses.expired")}</Badge>;
  }
  return (
    <Badge tone="success">
      {daysLeft === 1
        ? t("changes.statuses.lastDay")
        : t("changes.statuses.available", { count: daysLeft })}
    </Badge>
  );
}

/**
 * Undo one recorded change after a confirmation naming it. A refusal toasts its specific
 * reason and reloads the list, since another admin may have undone or changed it meanwhile.
 */
export function UndoChangeButton({ action }: { action: AdminActionOut }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const refresh = useRefreshQueries();
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const summary = changeSummary(t, action);

  async function undo() {
    setPending(true);
    const undone = await undoChange(action.id, queryClient, t("changes.undone"));
    if (!undone) await refresh("listAdminActions");
    setPending(false);
    setConfirming(false);
  }

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        aria-label={`${t("changes.undo")}: ${summary}`}
        onClick={() => setConfirming(true)}
      >
        <Undo2Icon />
        {t("changes.undo")}
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("changes.confirmTitle")}
        description={summary}
        cancelLabel={t("forms.cancel")}
        confirmLabel={t("changes.undo")}
        pending={pending}
        pendingLabel={t("changes.undoing")}
        onConfirm={() => void undo()}
      >
        <p className="text-sm text-muted-foreground">{t("changes.confirmHint")}</p>
      </ConfirmDialog>
    </>
  );
}
