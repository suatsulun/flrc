import { updateColumnMutation, type ColumnOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNotifyDone } from "./undo-toast";

/**
 * Rename one field: only its name in the subject's language changes (ADR-076). Grades stay
 * attached, and the Turkish wording and group stay as created. Enter saves, Escape cancels.
 */
export function RenameFieldDialog({
  column,
  semesterId,
  onClose,
  onRenamed,
}: {
  /** The field being renamed; the dialog is open while one is given. */
  column?: ColumnOut;
  /** The semester the field belongs to; omitted on the Fields page (the open semester). */
  semesterId?: number;
  onClose: () => void;
  onRenamed: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const notifyDone = useNotifyDone();
  const [draft, setDraft] = useState<string>();
  // Until the admin types, the box shows the field's current name.
  const name = draft ?? column?.name ?? "";
  const trimmed = name.trim();
  const unchanged = trimmed === column?.name;
  const language = column ? t(`subjects.${column.subject}`) : "";
  const close = () => {
    setDraft(undefined);
    onClose();
  };
  const rename = useMutation({
    ...updateColumnMutation(),
    onSuccess: async (updated, variables) => {
      notifyDone(
        t("columns.renamed", { previous: column?.name ?? "", name: variables.body.name }),
        updated.action_id,
      );
      close();
      await onRenamed();
    },
  });

  return (
    <Dialog
      open={Boolean(column)}
      onOpenChange={(open) => {
        if (!open && !rename.isPending) close();
      }}
    >
      <DialogContent showCloseButton={!rename.isPending}>
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (!column || !trimmed || unchanged || rename.isPending) return;
            rename.mutate({
              path: { column_id: column.id },
              query: semesterId ? { semester_id: semesterId } : undefined,
              body: { name: trimmed },
            });
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("columns.renameTitle")}</DialogTitle>
            <DialogDescription>{t("columns.renameHint", { language })}</DialogDescription>
          </DialogHeader>
          <Field label={t("columns.renameField", { language })}>
            {(id) => (
              <Input
                id={id}
                autoFocus
                value={name}
                disabled={rename.isPending}
                onChange={(event) => setDraft(event.currentTarget.value)}
              />
            )}
          </Field>
          <DialogFooter>
            <Button variant="outline" disabled={rename.isPending} onClick={close}>
              {t("forms.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={!trimmed || unchanged}
              pending={rename.isPending}
              pendingLabel={t("feedback.saving")}
            >
              {t("forms.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
