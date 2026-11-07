import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { undoAdminAction } from "@flrc/api-client";
import { errorMessage } from "./feedback";

/** How long a success toast keeps its Undo button; the change stays undoable for 7 days. */
const UNDO_TOAST_MS = 12_000;

/**
 * Undo one recorded admin change (ADR-075) and refresh every cached query, since an undo can
 * touch classes, rosters, fields and users at once. A refusal names its blocking reason.
 */
export async function undoChange(
  actionId: number,
  queryClient: QueryClient,
  successMessage: string,
): Promise<boolean> {
  try {
    await undoAdminAction({ path: { action_id: actionId }, throwOnError: true });
  } catch (error) {
    toast.error(errorMessage(error));
    return false;
  }
  toast.success(successMessage);
  await queryClient.invalidateQueries();
  return true;
}

/**
 * Report a finished admin write. When the API recorded it as undoable (`action_id`), the toast
 * offers Undo; the Recent changes page offers it for the rest of the retention window.
 */
export function useNotifyDone() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  return (message: string, actionId?: number | null) => {
    if (actionId == null) {
      toast.success(message);
      return;
    }
    toast.success(message, {
      duration: UNDO_TOAST_MS,
      action: {
        label: t("changes.undo"),
        onClick: () => void undoChange(actionId, queryClient, t("changes.undone")),
      },
    });
  };
}
