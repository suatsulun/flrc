import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  deleteUserSignatureMutation,
  listManagedUsersQueryKey,
  patchManagedUserMutation,
  uploadUserSignatureMutation,
} from "@flrc/api-client";
import type { ManagedUserOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";

export function TeacherReportIdentity({
  user,
  onClose,
}: {
  user: ManagedUserOut;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [name, setName] = useState(user.report_name ?? "");
  const [fileError, setFileError] = useState(false);
  const refresh = () => {
    toast.success(t("feedback.saved"));
    void client.invalidateQueries({ queryKey: listManagedUsersQueryKey() });
  };
  const patch = useMutation({ ...patchManagedUserMutation(), onSuccess: refresh });
  const upload = useMutation({ ...uploadUserSignatureMutation(), onSuccess: refresh });
  const remove = useMutation({ ...deleteUserSignatureMutation(), onSuccess: refresh });
  const pending = patch.isPending || upload.isPending || remove.isPending;

  return (
    <Dialog open onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent
        showCloseButton={!pending}
        className="max-h-[calc(100dvh-2rem)] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>{t("users.reportIdentity")}</DialogTitle>
          <DialogDescription>{user.full_name}</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            patch.mutate({
              path: { user_id: user.id },
              body: { report_name: name.trim() || null },
            });
          }}
        >
          <Field label={t("users.reportName")}>
            {(id) => (
              <Input
                id={id}
                value={name}
                maxLength={160}
                placeholder={user.full_name}
                disabled={pending}
                onChange={(event) => setName(event.target.value)}
              />
            )}
          </Field>
          <p className="text-xs text-muted-foreground">{t("users.reportNameHelp")}</p>
          <Button
            type="submit"
            disabled={pending}
            pending={patch.isPending}
            pendingLabel={t("feedback.saving")}
          >
            {t("forms.save")}
          </Button>
        </form>
        <div className="grid gap-3 border-t pt-4">
          {user.signature_url ? (
            <img
              src={user.signature_url}
              alt={t("users.signaturePreview", { name: user.full_name })}
              className="h-28 w-full rounded border bg-white object-contain p-2"
            />
          ) : (
            <p className="text-sm text-muted-foreground">{t("users.noSignature")}</p>
          )}
          <Field label={t("users.signatureUpload")}>
            {(id) => (
              <Input
                id={id}
                type="file"
                accept="image/png,.png"
                disabled={pending}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file) return;
                  setFileError(false);
                  if (file.size > 1024 * 1024 || !file.name.toLowerCase().endsWith(".png")) {
                    setFileError(true);
                    return;
                  }
                  upload.mutate({ path: { user_id: user.id }, body: { file } });
                }}
              />
            )}
          </Field>
          <p className="text-xs text-muted-foreground">{t("users.signatureHelp")}</p>
          {upload.isPending ? <p role="status">{t("feedback.saving")}</p> : null}
          {user.signature_url ? (
            <Button
              variant="outline"
              disabled={pending}
              pending={remove.isPending}
              pendingLabel={t("feedback.saving")}
              onClick={() => remove.mutate({ path: { user_id: user.id } })}
            >
              {t("users.signatureRemove")}
            </Button>
          ) : null}
          {fileError || upload.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {t("users.signatureInvalid")}
            </p>
          ) : null}
          {patch.isError || remove.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {t("users.saveFailed")}
            </p>
          ) : null}
        </div>
        <Button variant="ghost" disabled={pending} onClick={onClose}>
          {t("forms.close")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
