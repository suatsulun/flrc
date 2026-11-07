import { CountdownConfirmDialog } from "./countdown-confirm-dialog";

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
  return (
    <CountdownConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onStay();
      }}
      seconds={LEAVE_DELAY_SECONDS}
      title={title}
      description={description}
      cancelLabel={stayLabel}
      confirmLabel={leaveLabel}
      countdownLabel={countdownLabel}
      onConfirm={onLeave}
    />
  );
}
