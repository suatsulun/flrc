import { useBlocker, type ShouldBlockFn } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { LeaveGuardDialog } from "@flrc/ui/components/leave-guard-dialog";

// Only a different page leaves this one; search-param changes and following the link to the
// page already open stay. Document exits ask through `allowDocumentExit` with their destination.
const leavesPage: ShouldBlockFn = ({ current, next }) => current.pathname !== next.pathname;

/**
 * Asks before leaving the page while PDF sets are generating or queued.
 *
 * Router navigations and document exits that ask through `allowDocumentExit` get this dialog;
 * tab close, reload and typed URLs can only get the browser's own prompt.
 */
export function PdfLeaveGuard({ active, onLeave }: { active: boolean; onLeave: () => void }) {
  const { t } = useTranslation();
  // `disabled` re-registers the blocker whenever `active` changes, and `leavesPage` reads
  // nothing from render, so the router never consults a stale closure.
  const blocker = useBlocker({
    shouldBlockFn: leavesPage,
    enableBeforeUnload: true,
    disabled: !active,
    withResolver: true,
  });

  return (
    <LeaveGuardDialog
      open={blocker.status === "blocked"}
      onStay={() => {
        if (blocker.status === "blocked") blocker.reset();
      }}
      onLeave={() => {
        if (blocker.status !== "blocked") return;
        onLeave();
        blocker.proceed();
      }}
      title={t("reports.leaveTitle")}
      description={t("reports.leaveDescription")}
      stayLabel={t("forms.cancel")}
      leaveLabel={t("reports.leave")}
      countdownLabel={(seconds) => t("reports.leaveCountdown", { seconds })}
    />
  );
}
