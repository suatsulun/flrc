import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { PlusIcon } from "lucide-react";
import {
  createManagedUserMutation,
  deleteManagedUserMutation,
  listManagedUsersOptions,
  listManagedUsersQueryKey,
  patchManagedUserMutation,
  type ManagedUserOut,
  type ManagedUserWriteOut,
  type UserPatch,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardContent, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Checkbox } from "@flrc/ui/components/checkbox";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { CountdownConfirmDialog } from "@flrc/ui/components/countdown-confirm-dialog";
import { ConfirmDialog } from "@flrc/ui/components/dialog";
import { EmptyState } from "@flrc/ui/components/empty-state";
import {
  PhoneCardActions,
  PhoneCardField,
  PhoneCardFields,
  PhoneCardHeader,
  PhoneCardItem,
  PhoneCardList,
} from "@flrc/ui/components/phone-card-list";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
  TableScroll,
  TableText,
} from "@flrc/ui/components/table";
import { useIsPhone } from "@flrc/ui/hooks/use-is-phone";
import { cn } from "@flrc/ui/lib/utils";
import { AdminPage } from "../../admin/AdminPage";
import { USERS_ADD_FORM_GRID, UsersSkeleton } from "../../admin/page-skeletons";
import { TeacherReportIdentity } from "../../admin/TeacherReportIdentity";
import { useNotifyDone } from "../../admin/undo-toast";

export const Route = createFileRoute("/_auth/users")({ component: UsersPage });

type TeachingField = "english" | "german" | "french";
type TeachingStage = "primary" | "middle";
type UserConfirmation = {
  userId: number;
  name: string;
  action: "deactivate" | "resetIdentity";
};

/** Seconds the permanent-delete button stays locked each time its dialog opens (ADR-080). */
const DELETE_DELAY_SECONDS = 5;

/** Two row actions per line: a deactivated teacher's four actions wrap onto two lines. */
const ACTIONS_WIDTH = "w-[20rem]";

/** What a row control just changed, named for the success toast. */
function accountChangeMessage(t: TFunction, user: ManagedUserWriteOut, body: UserPatch): string {
  const name = user.full_name;
  if (body.reset_google_identity) return t("users.done.identityReset", { name });
  if (body.is_active != null) {
    return t(body.is_active ? "users.done.reactivated" : "users.done.deactivated", { name });
  }
  if (body.is_admin != null) {
    return t(body.is_admin ? "users.done.adminGranted" : "users.done.adminRevoked", { name });
  }
  if (body.is_coordinator != null) {
    return t(
      body.is_coordinator ? "users.done.coordinatorGranted" : "users.done.coordinatorRevoked",
      { name },
    );
  }
  if (body.teaching_field != null) {
    return t("users.done.teachingField", { name, value: t(`subjects.${user.teaching_field}`) });
  }
  return t("users.done.teachingStage", {
    name,
    value: user.teaching_stage ? t(`teachingStages.${user.teaching_stage}`) : "—",
  });
}

function UsersPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const notifyDone = useNotifyDone();
  // One layout at a time: the cards' selects must not exist hidden beside the table's.
  const isPhone = useIsPhone();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [teachingField, setTeachingField] = useState<TeachingField>("english");
  const [teachingStage, setTeachingStage] = useState<TeachingStage>("primary");
  const [search, setSearch] = useState("");
  const [confirmation, setConfirmation] = useState<UserConfirmation>();
  const [deletion, setDeletion] = useState<{ userId: number; name: string }>();
  const [reportUserId, setReportUserId] = useState<number>();
  const {
    data: users = [],
    isPending: usersPending,
    isError: usersError,
  } = useQuery(listManagedUsersOptions());
  const refresh = () => queryClient.invalidateQueries({ queryKey: listManagedUsersQueryKey() });
  const create = useMutation({
    ...createManagedUserMutation(),
    onSuccess: (created) => {
      setEmail("");
      setFullName("");
      notifyDone(t("users.done.created", { name: created.full_name }), created.action_id);
      void refresh();
    },
  });
  const patch = useMutation({
    ...patchManagedUserMutation(),
    onSuccess: (updated, { body }) => {
      setConfirmation(undefined);
      notifyDone(accountChangeMessage(t, updated, body), updated.action_id);
      void refresh();
    },
  });
  const remove = useMutation({
    ...deleteManagedUserMutation(),
    onSuccess: (_, { path }) => {
      // Permanent (ADR-080): the toast has no Undo, and the row leaves the list at once.
      notifyDone(t("users.done.deleted", { name: deletion?.name ?? "" }));
      setDeletion(undefined);
      queryClient.setQueryData<ManagedUserOut[]>(listManagedUsersQueryKey(), (current) =>
        current?.filter((item) => item.id !== path.user_id),
      );
      // Assignments, the dashboard and recorded changes all named this teacher.
      void queryClient.invalidateQueries();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({
      body: {
        email,
        full_name: fullName,
        teaching_field: teachingField,
        ...(teachingField === "english" ? { teaching_stage: teachingStage } : {}),
        is_admin: false,
        is_coordinator: false,
      },
    });
  }

  if (usersPending) return <UsersSkeleton />;
  if (usersError) return <EmptyState title={t("errors.load")} />;

  const normalizedSearch = search.trim().toLocaleLowerCase();
  const reportUser = users.find((user) => user.id === reportUserId);
  const visibleUsers = normalizedSearch
    ? users.filter((user) =>
        `${user.full_name} ${user.email}`.toLocaleLowerCase().includes(normalizedSearch),
      )
    : users;
  const emptyMessage = normalizedSearch ? t("users.noMatches") : t("users.empty");

  // A teacher's controls, shared by the table row and the phone card so both act the same.
  function teachingFieldSelect(user: ManagedUserOut, className: string) {
    return (
      <NativeSelect
        className={className}
        aria-label={`${user.full_name} — ${t("users.teachingField")}`}
        value={user.teaching_field}
        disabled={patch.isPending}
        onChange={(event) =>
          patch.mutate({
            path: { user_id: user.id },
            body: {
              teaching_field: event.target.value as TeachingField,
            },
          })
        }
      >
        <option value="english">{t("subjects.english")}</option>
        <option value="german">{t("subjects.german")}</option>
        <option value="french">{t("subjects.french")}</option>
      </NativeSelect>
    );
  }

  function teachingStageSelect(user: ManagedUserOut, className: string) {
    return (
      <NativeSelect
        className={className}
        aria-label={`${user.full_name} — ${t("users.teachingStage")}`}
        value={user.teaching_stage ?? "primary"}
        disabled={patch.isPending}
        onChange={(event) =>
          patch.mutate({
            path: { user_id: user.id },
            body: { teaching_stage: event.target.value as TeachingStage },
          })
        }
      >
        <option value="primary">{t("teachingStages.primary")}</option>
        <option value="middle">{t("teachingStages.middle")}</option>
      </NativeSelect>
    );
  }

  function roleCheckbox(user: ManagedUserOut, role: "admin" | "coordinator") {
    return (
      <Checkbox
        aria-label={`${user.full_name} — ${t(`users.${role}`)}`}
        checked={role === "admin" ? user.is_admin : user.is_coordinator}
        disabled={patch.isPending}
        onCheckedChange={(checked) =>
          patch.mutate({
            path: { user_id: user.id },
            body:
              role === "admin"
                ? { is_admin: checked === true }
                : { is_coordinator: checked === true },
          })
        }
      />
    );
  }

  function statusBadge(user: ManagedUserOut) {
    return (
      <Badge tone={user.is_active ? "success" : "neutral"}>
        {user.is_active ? t("users.active") : t("users.inactive")}
      </Badge>
    );
  }

  /** The row's actions in order; a deactivated teacher also gets reset and permanent delete. */
  function actionButtons(user: ManagedUserOut, className?: string) {
    return (
      <>
        <Button
          size="sm"
          variant="outline"
          className={className}
          onClick={() => setReportUserId(user.id)}
        >
          {t("users.reportIdentity")}
        </Button>
        {!user.is_active ? (
          <Button
            size="sm"
            variant="ghost"
            className={className}
            disabled={patch.isPending}
            onClick={() =>
              setConfirmation({
                userId: user.id,
                name: user.full_name,
                action: "resetIdentity",
              })
            }
          >
            {t("users.resetIdentity")}
          </Button>
        ) : null}
        <Button
          size="sm"
          variant={user.is_active ? "destructive" : "outline"}
          className={className}
          pending={patch.isPending && patch.variables?.path.user_id === user.id}
          pendingLabel={t("feedback.saving")}
          onClick={() => {
            if (user.is_active) {
              setConfirmation({
                userId: user.id,
                name: user.full_name,
                action: "deactivate",
              });
              return;
            }
            patch.mutate({
              path: { user_id: user.id },
              body: { is_active: true },
            });
          }}
        >
          {user.is_active ? t("users.deactivate") : t("users.reactivate")}
        </Button>
        {!user.is_active ? (
          <Button
            size="sm"
            variant="outline"
            className={cn(
              "border-destructive/40 text-destructive hover:border-destructive/60 hover:bg-destructive/10 hover:text-destructive",
              className,
            )}
            disabled={patch.isPending || remove.isPending}
            onClick={() => setDeletion({ userId: user.id, name: user.full_name })}
          >
            {t("users.delete")}
          </Button>
        ) : null}
      </>
    );
  }

  return (
    <AdminPage title={t("users.title")} description={t("users.description")}>
      <Card>
        <CardHeader>
          <CardTitle>{t("users.allow")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className={USERS_ADD_FORM_GRID} onSubmit={submit}>
            <Field label={t("users.email")}>
              {(id) => (
                <Input
                  id={id}
                  type="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              )}
            </Field>
            <Field label={t("users.fullName")}>
              {(id) => (
                <Input
                  id={id}
                  required
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                />
              )}
            </Field>
            <Field label={t("users.teachingField")}>
              {(id) => (
                <NativeSelect
                  id={id}
                  value={teachingField}
                  onChange={(event) => setTeachingField(event.target.value as TeachingField)}
                >
                  <option value="english">{t("subjects.english")}</option>
                  <option value="german">{t("subjects.german")}</option>
                  <option value="french">{t("subjects.french")}</option>
                </NativeSelect>
              )}
            </Field>
            <Field label={t("users.teachingStage")}>
              {(id) => (
                <NativeSelect
                  id={id}
                  value={teachingStage}
                  disabled={teachingField !== "english"}
                  onChange={(event) => setTeachingStage(event.target.value as TeachingStage)}
                >
                  <option value="primary">{t("teachingStages.primary")}</option>
                  <option value="middle">{t("teachingStages.middle")}</option>
                </NativeSelect>
              )}
            </Field>
            <Button
              type="submit"
              className="w-full sm:w-auto sm:self-end"
              pending={create.isPending}
              pendingLabel={t("feedback.saving")}
            >
              <PlusIcon />
              {t("users.allow")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("users.title")}</CardTitle>
          <Input
            className="w-full sm:w-72"
            type="search"
            value={search}
            aria-label={t("users.search")}
            placeholder={t("users.search")}
            onChange={(event) => setSearch(event.currentTarget.value)}
          />
        </CardHeader>
        {isPhone ? (
          visibleUsers.length === 0 ? (
            <CardBody>
              <p className="px-5 py-6 text-sm text-muted-foreground">{emptyMessage}</p>
            </CardBody>
          ) : (
            <PhoneCardList aria-label={t("users.tableLabel")}>
              {visibleUsers.map((user) => (
                <PhoneCardItem key={user.id} data-testid="user-card">
                  <PhoneCardHeader
                    title={user.full_name}
                    subtitle={<span className="break-all">{user.email}</span>}
                    status={statusBadge(user)}
                  />
                  <PhoneCardFields>
                    <PhoneCardField label={t("users.teachingField")}>
                      {teachingFieldSelect(user, "w-full")}
                    </PhoneCardField>
                    <PhoneCardField label={t("users.teachingStage")}>
                      {user.teaching_field === "english" ? (
                        teachingStageSelect(user, "w-full")
                      ) : (
                        <span className="flex h-10 items-center text-sm text-muted-foreground">
                          —
                        </span>
                      )}
                    </PhoneCardField>
                    {(["admin", "coordinator"] as const).map((role) => (
                      <label
                        key={role}
                        className="flex min-h-10 cursor-pointer items-center gap-2.5 rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm font-medium"
                      >
                        {roleCheckbox(user, role)}
                        {t(`users.${role}`)}
                      </label>
                    ))}
                  </PhoneCardFields>
                  <PhoneCardActions>{actionButtons(user, "w-full")}</PhoneCardActions>
                </PhoneCardItem>
              ))}
            </PhoneCardList>
          )
        ) : (
          <CardBody>
            <TableScroll aria-label={t("users.tableLabel")}>
              {/* Fills the card at every width: the person column takes the spare width and every
                other column hugs its content (`w-px`), so the actions meet the card's right edge.
                Name and e-mail share one column so the whole row fits a 1440px screen. */}
              <Table className="w-full">
                <TableCaption>{t("users.tableLabel")}</TableCaption>
                <TableHead>
                  <tr>
                    <TableHeader className="z-30 min-w-40 border-r bg-muted/95 sm:left-0">
                      {t("users.fullName")} · {t("users.email")}
                    </TableHeader>
                    <TableHeader className="w-px whitespace-normal">
                      {t("users.teachingField")}
                    </TableHeader>
                    <TableHeader className="w-px whitespace-normal">
                      {t("users.teachingStage")}
                    </TableHeader>
                    <TableHeader className="w-px" align="center">
                      {t("users.admin")}
                    </TableHeader>
                    <TableHeader className="w-px" align="center">
                      {t("users.coordinator")}
                    </TableHeader>
                    <TableHeader className="w-px">{t("users.status")}</TableHeader>
                    <TableHeader className="w-px" align="right">
                      {t("users.actions")}
                    </TableHeader>
                  </tr>
                </TableHead>
                <TableBody>
                  {visibleUsers.length === 0 ? (
                    <TableEmpty colSpan={7}>{emptyMessage}</TableEmpty>
                  ) : (
                    visibleUsers.map((user) => (
                      <TableRow key={user.id}>
                        <TableCell className="z-10 border-r bg-card group-even:bg-muted group-hover:bg-accent sm:sticky sm:left-0">
                          <TableText className="max-w-40 font-medium sm:max-w-52 2xl:max-w-80">
                            {user.full_name}
                          </TableText>
                          <TableText className="max-w-40 text-xs text-muted-foreground sm:max-w-52 2xl:max-w-80">
                            {user.email}
                          </TableText>
                        </TableCell>
                        <TableCell>{teachingFieldSelect(user, "w-auto")}</TableCell>
                        <TableCell>
                          {user.teaching_field === "english" ? (
                            teachingStageSelect(user, "w-auto")
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell align="center">{roleCheckbox(user, "admin")}</TableCell>
                        <TableCell align="center">{roleCheckbox(user, "coordinator")}</TableCell>
                        <TableCell>{statusBadge(user)}</TableCell>
                        <TableCell align="right">
                          <div
                            className={`ml-auto flex flex-wrap justify-end gap-2 ${ACTIONS_WIDTH}`}
                          >
                            {actionButtons(user)}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableScroll>
          </CardBody>
        )}
      </Card>

      {reportUser ? (
        <TeacherReportIdentity
          key={reportUser.id}
          user={reportUser}
          onClose={() => setReportUserId(undefined)}
        />
      ) : null}
      <ConfirmDialog
        open={Boolean(confirmation)}
        onOpenChange={(open) => !open && setConfirmation(undefined)}
        title={
          confirmation?.action === "resetIdentity"
            ? t("users.resetIdentity")
            : t("users.deactivate")
        }
        description={
          confirmation?.action === "resetIdentity"
            ? t("users.resetIdentityConfirm", { name: confirmation.name })
            : t("users.deactivateConfirm", { name: confirmation?.name })
        }
        cancelLabel={t("forms.cancel")}
        confirmLabel={
          confirmation?.action === "resetIdentity"
            ? t("users.resetIdentity")
            : t("users.deactivate")
        }
        destructive
        pending={patch.isPending}
        pendingLabel={t("feedback.saving")}
        onConfirm={() => {
          if (!confirmation) return;
          patch.mutate({
            path: { user_id: confirmation.userId },
            body:
              confirmation.action === "resetIdentity"
                ? { reset_google_identity: true }
                : { is_active: false },
          });
        }}
      />
      <CountdownConfirmDialog
        open={Boolean(deletion)}
        onOpenChange={(open) => !open && setDeletion(undefined)}
        seconds={DELETE_DELAY_SECONDS}
        danger
        title={t("users.deleteTitle", { name: deletion?.name })}
        description={t("users.deleteDescription")}
        cancelLabel={t("forms.cancel")}
        confirmLabel={t("users.delete")}
        countdownLabel={(seconds) => t("users.deleteCountdown", { seconds })}
        pending={remove.isPending}
        pendingLabel={t("feedback.saving")}
        onConfirm={() => {
          if (deletion) remove.mutate({ path: { user_id: deletion.userId } });
        }}
      >
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <section className="space-y-1.5">
            <h3 className="font-semibold text-destructive">{t("users.deleteErased")}</h3>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>{t("users.deleteErasedIdentity")}</li>
              <li>{t("users.deleteErasedReport")}</li>
              <li>{t("users.deleteErasedAccess")}</li>
            </ul>
          </section>
          <section className="space-y-1.5">
            <h3 className="font-semibold">{t("users.deleteKept")}</h3>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>{t("users.deleteKeptGrades")}</li>
              <li>{t("users.deleteKeptEmail")}</li>
            </ul>
          </section>
        </div>
      </CountdownConfirmDialog>
    </AdminPage>
  );
}
