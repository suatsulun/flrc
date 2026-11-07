import { Checkbox } from "@flrc/ui/components/checkbox";
import { ConfirmDialog } from "@flrc/ui/components/dialog";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { skipMoveConfirmation } from "./move-confirmation";

/** Names listed by the dialog before it summarizes the rest as a count. */
const LISTED_NAMES = 5;

export type MoveRequest = {
  studentIds: number[];
  names: string[];
  fromClasses: string[];
  targetClassId: number;
  targetClass: string;
};

/**
 * Confirm a student move before it is sent: who moves, from which class and to which one.
 * Cancelling changes nothing; "do not ask again" holds until the browser session ends.
 */
export function MoveStudentsDialog({
  request,
  pending,
  onCancel,
  onConfirm,
}: {
  request?: MoveRequest;
  pending: boolean;
  onCancel: () => void;
  onConfirm: (request: MoveRequest) => void;
}) {
  const { t } = useTranslation();
  const [skipAgain, setSkipAgain] = useState(false);
  const skipLabelId = useId();
  const names = request?.names ?? [];
  const from = request?.fromClasses.join(", ") ?? "";
  const target = request?.targetClass ?? "";
  const hidden = names.length - LISTED_NAMES;

  return (
    <ConfirmDialog
      open={Boolean(request)}
      onOpenChange={(open) => {
        if (open) return;
        setSkipAgain(false);
        onCancel();
      }}
      title={t("classWorkspace.moveTitle")}
      description={
        names.length === 1
          ? t("classWorkspace.moveConfirmOne", { name: names[0], from, target })
          : t("classWorkspace.moveConfirmMany", { count: names.length, from, target })
      }
      cancelLabel={t("forms.cancel")}
      confirmLabel={t("roster.move")}
      pending={pending}
      pendingLabel={t("classWorkspace.movingStudent")}
      onConfirm={() => {
        if (!request) return;
        if (skipAgain) skipMoveConfirmation();
        setSkipAgain(false);
        onConfirm(request);
      }}
    >
      <div className="space-y-3">
        {names.length > 1 ? (
          <ul className="list-disc space-y-0.5 pl-5 text-sm" data-testid="move-student-names">
            {names.slice(0, LISTED_NAMES).map((name, index) => (
              <li key={`${index}-${name}`}>{name}</li>
            ))}
            {hidden > 0 ? (
              <li className="list-none text-muted-foreground">
                {t("classWorkspace.moveMore", { count: hidden })}
              </li>
            ) : null}
          </ul>
        ) : null}
        <p className="text-sm text-muted-foreground">{t("classWorkspace.moveKeeps")}</p>
        <label className="flex items-center gap-2.5 text-sm">
          <Checkbox
            aria-labelledby={skipLabelId}
            checked={skipAgain}
            disabled={pending}
            onCheckedChange={(value) => setSkipAgain(value === true)}
          />
          <span id={skipLabelId}>{t("classWorkspace.moveSkipAgain")}</span>
        </label>
      </div>
    </ConfirmDialog>
  );
}
