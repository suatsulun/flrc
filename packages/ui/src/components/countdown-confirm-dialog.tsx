import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { ConfirmDialog } from "./dialog";

/**
 * A confirmation whose confirm button stays disabled, showing the seconds left, for a
 * moment every time the dialog opens, so a reflexive click cannot trigger an irreversible
 * action. Cancel works from the start. The wait is a plain timer, with no animation.
 */
export function CountdownConfirmDialog({
  open,
  onOpenChange,
  seconds,
  title,
  description,
  children,
  cancelLabel,
  confirmLabel,
  countdownLabel,
  onConfirm,
  destructive = true,
  pending,
  pendingLabel,
  finalFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** How long the confirm button stays locked after each opening. */
  seconds: number;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  cancelLabel: string;
  confirmLabel: string;
  /** The locked confirm button's label, e.g. `Delete (3)`. */
  countdownLabel: (secondsLeft: number) => string;
  onConfirm: () => void;
  destructive?: boolean;
  pending?: boolean;
  pendingLabel?: string;
  finalFocus?: ComponentProps<typeof ConfirmDialog>["finalFocus"];
}) {
  const [secondsLeft, setSecondsLeft] = useState(seconds);
  const [wasOpen, setWasOpen] = useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) setSecondsLeft(seconds);
  }
  useEffect(() => {
    if (!open) return;
    // Counting against a deadline keeps a throttled background tab from stretching the wait.
    const deadline = Date.now() + seconds * 1000;
    const timer = window.setInterval(() => {
      const left = Math.max(Math.ceil((deadline - Date.now()) / 1000), 0);
      setSecondsLeft(left);
      if (left === 0) window.clearInterval(timer);
    }, 250);
    return () => window.clearInterval(timer);
  }, [open, seconds]);

  const locked = secondsLeft > 0;
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      cancelLabel={cancelLabel}
      confirmLabel={locked ? countdownLabel(secondsLeft) : confirmLabel}
      confirmDisabled={locked}
      destructive={destructive}
      pending={pending}
      pendingLabel={pendingLabel}
      finalFocus={finalFocus}
      onConfirm={() => {
        if (!locked) onConfirm();
      }}
    >
      {children}
    </ConfirmDialog>
  );
}
