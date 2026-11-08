import { useEffect, useState } from "react";
import { ConfirmDialog } from "./dialog";

const LEAVE_DELAY_SECONDS = 4;

/**
 * Asks before leaving a page whose file is still being prepared. The Leave button stays
 * disabled for a few seconds every time the dialog opens, so a reflexive click cannot discard
 * the work. Each app wires `open`, `onStay` and `onLeave` to its router's blocker.
 */
export function LeaveGuardDialog({
  open,
  onStay,
  onLeave,
  title,
  description,
  stayLabel,
  leaveLabel,
  countdownLabel,
}: {
  open: boolean;
  onStay: () => void;
  onLeave: () => void;
  title: string;
  description: string;
  stayLabel: string;
  leaveLabel: string;
  countdownLabel: (seconds: number) => string;
}) {
  const [secondsLeft, setSecondsLeft] = useState(LEAVE_DELAY_SECONDS);
  const [wasOpen, setWasOpen] = useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) setSecondsLeft(LEAVE_DELAY_SECONDS);
  }
  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(
      () => setSecondsLeft((seconds) => Math.max(seconds - 1, 0)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [open]);

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onStay();
      }}
      title={title}
      description={description}
      cancelLabel={stayLabel}
      confirmLabel={secondsLeft > 0 ? countdownLabel(secondsLeft) : leaveLabel}
      confirmDisabled={secondsLeft > 0}
      destructive
      onConfirm={onLeave}
    />
  );
}
