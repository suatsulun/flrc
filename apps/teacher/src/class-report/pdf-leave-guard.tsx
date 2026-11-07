import { LeaveGuardDialog } from "@flrc/ui/components/leave-guard-dialog";
import { useBlocker, type ShouldBlockFn } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

// Only a different page leaves this one; changing the semester in the address stays.
const leavesPage: ShouldBlockFn = ({ current, next }) => current.pathname !== next.pathname;

/**
 * Asks before leaving the class report while its PDF is being prepared. Router navigations get
 * this dialog; tab close, reload and typed URLs can only get the browser's own prompt.
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
