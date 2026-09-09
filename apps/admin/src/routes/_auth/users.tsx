import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { PlusIcon } from "lucide-react";
import { toast } from "sonner";
import {
  createManagedUserMutation,
  listManagedUsersOptions,
  listManagedUsersQueryKey,
  patchManagedUserMutation,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardContent, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Checkbox } from "@flrc/ui/components/checkbox";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { ConfirmDialog } from "@flrc/ui/components/dialog";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
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
import { AdminPage } from "../../admin/AdminPage";

export const Route = createFileRoute("/_auth/users")({ component: UsersPage });

type TeachingField = "english" | "german" | "french";
type TeachingStage = "primary" | "middle";
type UserConfirmation = {
  userId: number;
  name: string;
  action: "deactivate" | "resetIdentity";
};

function UsersPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [teachingField, setTeachingField] = useState<TeachingField>("english");
  const [teachingStage, setTeachingStage] = useState<TeachingStage>("primary");
  const [search, setSearch] = useState("");
  const [confirmation, setConfirmation] = useState<UserConfirmation>();
  const {
    data: users = [],
    isPending: usersPending,
    isError: usersError,
  } = useQuery(listManagedUsersOptions());
  const refresh = () => queryClient.invalidateQueries({ queryKey: listManagedUsersQueryKey() });
  const create = useMutation({
    ...createManagedUserMutation(),
    onSuccess: () => {
      setEmail("");
      setFullName("");
      toast.success(t("users.allowedSuccess"));
      void refresh();
    },
  });
  const patch = useMutation({
    ...patchManagedUserMutation(),
    onSuccess: () => {
      setConfirmation(undefined);
      toast.success(t("feedback.saved"));
      void refresh();
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

  if (usersPending) return <PageSkeleton />;
  if (usersError) return <EmptyState title={t("errors.load")} />;

  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleUsers = normalizedSearch
    ? users.filter((user) =>
        `${user.full_name} ${user.email}`.toLocaleLowerCase().includes(normalizedSearch),
      )
    : users;

  return (
    <AdminPage title={t("users.title")} description={t("users.description")}>
      {create.isError || patch.isError ? (
        <p
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive-surface px-4 py-3 text-sm text-destructive"
        >
          {t("users.saveFailed")}
        </p>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>{t("users.allow")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_11rem_11rem_auto]"
            onSubmit={submit}
          >
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
              className="self-end"
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
        <CardBody>
          <TableScroll aria-label={t("users.tableLabel")}>
            <Table className="min-w-[76rem]">
              <TableCaption>{t("users.tableLabel")}</TableCaption>
              <TableHead>
                <tr>
                  <TableHeader className="sticky left-0 z-30 min-w-48 border-r bg-muted/95">
                    {t("users.fullName")}
                  </TableHeader>
                  <TableHeader className="min-w-64">{t("users.email")}</TableHeader>
                  <TableHeader>{t("users.teachingField")}</TableHeader>
                  <TableHeader>{t("users.teachingStage")}</TableHeader>
                  <TableHeader align="center">{t("users.admin")}</TableHeader>
                  <TableHeader align="center">{t("users.coordinator")}</TableHeader>
                  <TableHeader>{t("users.status")}</TableHeader>
                  <TableHeader align="right">{t("users.actions")}</TableHeader>
                </tr>
              </TableHead>
              <TableBody>
                {visibleUsers.length === 0 ? (
                  <TableEmpty colSpan={8}>
                    {normalizedSearch ? t("users.noMatches") : t("users.empty")}
                  </TableEmpty>
                ) : (
                  visibleUsers.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell className="sticky left-0 z-10 border-r bg-card font-medium group-even:bg-muted group-hover:bg-accent">
                        <TableText className="max-w-48">{user.full_name}</TableText>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        <TableText className="max-w-64">{user.email}</TableText>
                      </TableCell>
                      <TableCell>
                        <NativeSelect
                          className="w-32"
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
                      </TableCell>
                      <TableCell>
                        {user.teaching_field === "english" ? (
                          <NativeSelect
                            className="w-32"
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
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell align="center">
                        <Checkbox
                          aria-label={t("users.admin")}
                          checked={user.is_admin}
                          disabled={patch.isPending}
                          onCheckedChange={(checked) =>
                            patch.mutate({
                              path: { user_id: user.id },
                              body: { is_admin: checked === true },
                            })
                          }
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Checkbox
                          aria-label={t("users.coordinator")}
                          checked={user.is_coordinator}
                          disabled={patch.isPending}
                          onCheckedChange={(checked) =>
                            patch.mutate({
                              path: { user_id: user.id },
                              body: { is_coordinator: checked === true },
                            })
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Badge tone={user.is_active ? "success" : "neutral"}>
                          {user.is_active ? t("users.active") : t("users.inactive")}
                        </Badge>
                      </TableCell>
                      <TableCell align="right">
                        <div className="flex justify-end gap-2">
                          {!user.is_active ? (
                            <Button
                              size="sm"
                              variant="ghost"
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
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableScroll>
        </CardBody>
      </Card>

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
    </AdminPage>
  );
}
