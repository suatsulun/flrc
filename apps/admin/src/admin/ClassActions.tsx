import { GRADES, gradeLabel } from "@flrc/i18n";
import {
  deleteAdminClassMutation,
  listAssignmentMatrixOptions,
  patchAdminClassMutation,
  type AdminClassOut,
  type AdminClassWriteOut,
} from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import {
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PencilIcon, Trash2Icon } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNotifyDone } from "./undo-toast";
import { useReturnFocus } from "./use-return-focus";

/**
 * Edit a class's grade and section, or delete it. Deleting is offered only in a setup year for a
 * class without students or teachers; the reason is shown otherwise, and the API still refuses
 * a class that holds saved grades.
 */
export function ClassActions({
  schoolClass,
  yearStatus,
  onEdited,
  onDeleted,
}: {
  schoolClass: AdminClassOut;
  yearStatus: string;
  onEdited: (updated: AdminClassWriteOut) => Promise<unknown>;
  onDeleted: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const notifyDone = useNotifyDone();
  const reasonId = useId();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const dialogFocus = useReturnFocus();
  const { data: matrix = [] } = useQuery(
    listAssignmentMatrixOptions({ path: { year_id: schoolClass.year_id } }),
  );
  const hasTeachers = matrix.some((slot) => slot.class_id === schoolClass.id);
  const deleteBlocked =
    yearStatus !== "setup"
      ? t("classes.deleteSetupOnly")
      : schoolClass.student_count > 0
        ? t("classes.deleteHasStudents")
        : hasTeachers
          ? t("classes.deleteHasTeachers")
          : undefined;
  const remove = useMutation({
    ...deleteAdminClassMutation(),
    // The toast names the class that was confirmed, captured when the delete is sent.
    onMutate: () => ({ className: schoolClass.name }),
    onSuccess: async (result, _variables, submitted) => {
      setDeleting(false);
      notifyDone(t("classes.deleted", submitted), result.action_id);
      await onDeleted();
    },
  });

  return (
    <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
      {deleteBlocked ? (
        <p id={reasonId} className="text-xs text-muted-foreground">
          {deleteBlocked}
        </p>
      ) : null}
      <Button
        variant="outline"
        size="sm"
        onClick={(event) => {
          dialogFocus.remember(event.currentTarget);
          setEditing(true);
        }}
      >
        <PencilIcon />
        {t("classes.edit")}
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={Boolean(deleteBlocked)}
        aria-describedby={deleteBlocked ? reasonId : undefined}
        onClick={(event) => {
          dialogFocus.remember(event.currentTarget);
          setDeleting(true);
        }}
      >
        <Trash2Icon />
        {t("classes.delete")}
      </Button>
      <ClassEditDialog
        schoolClass={schoolClass}
        open={editing}
        finalFocus={dialogFocus.finalFocus}
        onClose={() => setEditing(false)}
        onEdited={async (updated, previous) => {
          notifyDone(
            t("classes.updated", { previous, className: updated.name }),
            updated.action_id,
          );
          setEditing(false);
          await onEdited(updated);
        }}
      />
      <ConfirmDialog
        finalFocus={dialogFocus.finalFocus}
        open={deleting}
        onOpenChange={(open) => !open && setDeleting(false)}
        title={t("classes.deleteTitle", { className: schoolClass.name })}
        description={t("classes.deleteConfirm", { className: schoolClass.name })}
        cancelLabel={t("forms.cancel")}
        confirmLabel={t("classes.delete")}
        destructive
        pending={remove.isPending}
        pendingLabel={t("feedback.saving")}
        onConfirm={() => remove.mutate({ path: { class_id: schoolClass.id } })}
      />
    </div>
  );
}

function ClassEditDialog({
  schoolClass,
  open,
  finalFocus,
  onClose,
  onEdited,
}: {
  schoolClass: AdminClassOut;
  open: boolean;
  finalFocus: () => HTMLElement | boolean;
  onClose: () => void;
  /** Receives the saved class and the name it had when the edit was sent. */
  onEdited: (updated: AdminClassWriteOut, previous: string) => Promise<unknown>;
}) {
  const { t } = useTranslation();
  // Until the admin changes them, the fields show the class as stored.
  const [draftGrade, setGrade] = useState<number>();
  const [draftSection, setSection] = useState<string>();
  const grade = draftGrade ?? schoolClass.grade_level;
  const section = draftSection ?? schoolClass.section;
  const close = () => {
    setGrade(undefined);
    setSection(undefined);
    onClose();
  };
  const edit = useMutation({
    ...patchAdminClassMutation(),
    onMutate: () => ({ previous: schoolClass.name }),
    onSuccess: async (updated, _variables, submitted) => {
      setGrade(undefined);
      setSection(undefined);
      await onEdited(updated, submitted.previous);
    },
  });
  const trimmed = section.trim();
  const unchanged = grade === schoolClass.grade_level && trimmed === schoolClass.section;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !edit.isPending) close();
      }}
    >
      <DialogContent showCloseButton={!edit.isPending} finalFocus={finalFocus}>
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (!trimmed || unchanged || edit.isPending) return;
            edit.mutate({
              path: { class_id: schoolClass.id },
              body: { grade_level: grade, section: trimmed },
            });
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("classes.editTitle", { className: schoolClass.name })}</DialogTitle>
            <DialogDescription>{t("classes.editHint")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("classes.gradeLevel")}>
              {(id) => (
                <NativeSelect
                  id={id}
                  value={grade}
                  disabled={edit.isPending}
                  onChange={(event) => setGrade(Number(event.target.value))}
                >
                  {GRADES.map((item) => (
                    <option key={item} value={item}>
                      {gradeLabel(t, item)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label={t("classes.section")}>
              {(id) => (
                <Input
                  id={id}
                  autoFocus
                  value={section}
                  disabled={edit.isPending}
                  onChange={(event) => setSection(event.currentTarget.value)}
                />
              )}
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={edit.isPending} onClick={close}>
              {t("forms.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={!trimmed || unchanged}
              pending={edit.isPending}
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
