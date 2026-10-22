import { useEffect, useState } from "react";
import { deepEqual, useBlocker, type ShouldBlockFn } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@flrc/ui/components/dialog";

const LEAVE_DELAY_SECONDS = 4;

// Navigations that only change search params stay on the page. Document exits (the teacher
// panel link, sign-out) reach the blocker with next equal to current, so they block as well.
const leavesPage: ShouldBlockFn = ({ current, next }) =>
  current.pathname !== next.pathname || deepEqual(current.search, next.search);

/**
 * Asks before leaving the page while PDF sets are generating or queued.
 *
 * Router navigations and document exits routed through the router get this dialog;
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
  const blocked = blocker.status === "blocked";

  // Leave stays disabled for a few seconds every time the dialog opens.
  const [secondsLeft, setSecondsLeft] = useState(LEAVE_DELAY_SECONDS);
  const [wasBlocked, setWasBlocked] = useState(blocked);
  if (wasBlocked !== blocked) {
    setWasBlocked(blocked);
    if (blocked) setSecondsLeft(LEAVE_DELAY_SECONDS);
  }
  useEffect(() => {
    if (!blocked) return;
    const timer = window.setInterval(
      () => setSecondsLeft((seconds) => Math.max(seconds - 1, 0)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [blocked]);

  return (
    <ConfirmDialog
      open={blocked}
      onOpenChange={(open) => {
        if (!open && blocker.status === "blocked") blocker.reset();
      }}
      title={t("reports.leaveTitle")}
      description={t("reports.leaveDescription")}
      cancelLabel={t("forms.cancel")}
      confirmLabel={
        secondsLeft > 0 ? t("reports.leaveCountdown", { seconds: secondsLeft }) : t("reports.leave")
      }
      confirmDisabled={secondsLeft > 0}
      destructive
      onConfirm={() => {
        if (blocker.status !== "blocked") return;
        onLeave();
        blocker.proceed();
      }}
    />
  );
}
