import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { undoAdminAction } from "@flrc/api-client";
import { errorMessage } from "./feedback";

/** How long a success toast keeps its Undo button; the change stays undoable for 7 days. */
const UNDO_TOAST_MS = 12_000;

/**
 * Reload every cached Recent changes list (the dashboard card and the paged /changes list
 * share the generated `listAdminActions` operation id), so a new or undone change shows at once.
 */
function refreshRecentChanges(queryClient: QueryClient) {
  return queryClient.invalidateQueries({
    predicate: ({ queryKey }) => {
      const head = queryKey[0];
      return (
        typeof head === "object" &&
        head !== null &&
        "_id" in head &&
        head._id === "listAdminActions"
      );
    },
  });
}

/**
 * Undo one recorded admin change (ADR-075) and refresh every cached query, since an undo can
 * touch classes, rosters, fields and users at once. A refusal names its blocking reason and
 * reloads the change lists, since another admin may have undone or changed it meanwhile.
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
    await refreshRecentChanges(queryClient);
    return false;
  }
  toast.success(successMessage);
  await queryClient.invalidateQueries();
  return true;
}

/**
 * Report a finished admin write. When the API recorded it as undoable (`action_id`), the toast
 * offers Undo and the Recent changes lists reload to include it; they offer Undo for the rest of
 * the retention window.
 */
export function useNotifyDone() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  return (message: string, actionId?: number | null) => {
    if (actionId == null) {
      toast.success(message);
      return;
    }
    void refreshRecentChanges(queryClient);
    toast.success(message, {
      duration: UNDO_TOAST_MS,
      action: {
        label: t("changes.undo"),
        onClick: () => void undoChange(actionId, queryClient, t("changes.undone")),
      },
    });
  };
}
