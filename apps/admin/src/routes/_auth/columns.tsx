import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { GRADES, gradeLabel } from "@flrc/i18n";
import { ChevronDownIcon, ChevronUpIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";
import {
  createColumnMutation,
  deleteColumnMutation,
  listColumnsOptions,
  reorderColumns,
  type ColumnOut,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody } from "@flrc/ui/components/card";
import { Checkbox } from "@flrc/ui/components/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  ConfirmDialog,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@flrc/ui/components/dialog";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { AdminPage } from "../../admin/AdminPage";
import { CopyFieldsDialog } from "../../admin/CopyFieldsDialog";
import { apiError } from "../../admin/feedback";
import { RenameFieldDialog } from "../../admin/RenameFieldDialog";
import { useNotifyDone } from "../../admin/undo-toast";
import { useRefreshQueries } from "../../admin/use-refresh-queries";
import { useReturnFocus } from "../../admin/use-return-focus";

const SUBJECTS = ["english", "german", "french"] as const;
type Subject = (typeof SUBJECTS)[number];

export const Route = createFileRoute("/_auth/columns")({
  validateSearch: (s): { grade: number; subject: Subject } => ({
    grade: GRADES.includes(Number(s.grade)) ? Number(s.grade) : 5,
    subject: SUBJECTS.includes(s.subject as Subject) ? (s.subject as Subject) : "english",
  }),
  component: ColumnsPage,
});

const formSchema = z.object({
  name: z.string().trim().min(1),
  group: z.string().trim(),
  turkish_name: z.string().trim(),
  turkish_group: z.string().trim(),
  value_type: z.enum(["score", "scale3", "text"]),
  owner_role: z.enum(["main", "skills", "german", "french"]),
  counts_in_average: z.boolean(),
});
type FormValues = z.infer<typeof formSchema>;

function ColumnsPage() {
  const { grade, subject } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { t } = useTranslation();
  const notifyDone = useNotifyDone();
  const refresh = useRefreshQueries();
  const query = { grade_level: grade, subject };
  const [pendingColumnId, setPendingColumnId] = useState<number>();
  const [deleteTarget, setDeleteTarget] = useState<ColumnOut>();
  const [renaming, setRenaming] = useState<ColumnOut>();
  const dialogFocus = useReturnFocus();
  const {
    data: columns = [],
    isPending: columnsPending,
    error: columnsError,
  } = useQuery(listColumnsOptions({ query }));
  // Without an open semester of the active year there is nothing to edit here.
  const locked = apiError(columnsError).code === "semester_locked";
  const invalidate = () => refresh("listColumns", "getGrid", "listClassCatalog");

  const reorder = useMutation({
    // The variables carry the moved field's name, so the toast names what was sent.
    mutationFn: async ({ ids }: { ids: number[]; name: string }) =>
      (await reorderColumns({ body: { ordered_ids: ids }, throwOnError: true })).data,
    onSuccess: (result, { name }) => {
      notifyDone(t("columns.reordered", { name }), result.action_id);
      void invalidate();
    },
    onSettled: () => setPendingColumnId(undefined),
  });
  const remove = useMutation({
    ...deleteColumnMutation(),
    // The toast names the field that was confirmed, captured when the delete is sent.
    onMutate: () => ({ name: deleteTarget?.name ?? "" }),
    onSuccess: (result, _variables, submitted) => {
      notifyDone(
        result.disabled ? t("columns.disabledKept", submitted) : t("columns.deleted", submitted),
        result.action_id,
      );
      setDeleteTarget(undefined);
      void invalidate();
    },
  });

  const move = (index: number, direction: -1 | 1) => {
    const ids = columns.map((column) => column.id);
    const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    setPendingColumnId(columns[index]?.id);
    reorder.mutate({ ids, name: columns[index].name });
  };

  if (columnsPending) return <PageSkeleton />;
  if (columnsError && !locked) return <EmptyState title={t("errors.load")} />;

  return (
    // The header controls act on the field list, so both share one column width instead of the
    // controls drifting to the far edge of a wide screen.
    <div className="max-w-3xl space-y-4">
      <AdminPage
        title={t("columns.title")}
        description={t("columns.description")}
        actions={
          <>
            <NativeSelect
              className="w-32"
              aria-label={t("classes.gradeLevel")}
              value={grade}
              onChange={(event) =>
                navigate({ search: { grade: Number(event.target.value), subject } })
              }
            >
              {GRADES.map((item) => (
                <option key={item} value={item}>
                  {gradeLabel(t, item)}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              className="w-36"
              aria-label={t("grid.subject")}
              value={subject}
              onChange={(event) =>
                navigate({ search: { grade, subject: event.target.value as Subject } })
              }
            >
              {SUBJECTS.map((item) => (
                <option key={item} value={item}>
                  {t(`subjects.${item}`)}
                </option>
              ))}
            </NativeSelect>
            {locked ? null : (
              <>
                <CopyFieldsDialog
                  grade={grade}
                  subject={subject}
                  columns={columns}
                  onCopied={(target) => {
                    void navigate({ search: target });
                    return invalidate();
                  }}
                />
                <CreateDialog
                  key={`${grade}-${subject}`}
                  grade={grade}
                  subject={subject}
                  onCreated={invalidate}
                />
              </>
            )}
          </>
        }
      >
        {locked ? (
          <EmptyState title={t("columns.lockedTitle")} description={t("columns.locked")} />
        ) : columns.length === 0 ? (
          <EmptyState title={t("columns.empty")} description={t("columns.emptyBody")} />
        ) : (
          <Card>
            <CardBody>
              <ul className="divide-y divide-border">
                {columns.map((column, index) => (
                  <li
                    key={column.id}
                    className={`flex items-center gap-3 px-4 py-2.5 ${column.is_active ? "" : "opacity-55"}`}
                  >
                    <span className="tabular w-6 text-xs text-muted-foreground">
                      {column.position}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{column.name}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
                        <Badge tone="outline">{t(`columns.valueTypes.${column.value_type}`)}</Badge>
                        <Badge tone="neutral">{t(`roles.${column.owner_role}`)}</Badge>
                        {column.counts_in_average ? (
                          <Badge tone="info" title={t("columns.countsInAverage")}>
                            Ø
                          </Badge>
                        ) : null}
                        {column.is_active ? null : (
                          <Badge tone="warning">{t("columns.disabled")}</Badge>
                        )}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-0.5">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={t("columns.moveUpColumn", { name: column.name })}
                        disabled={index === 0 || Boolean(pendingColumnId)}
                        pending={pendingColumnId === column.id && reorder.isPending}
                        pendingLabel={t("feedback.saving")}
                        onClick={() => move(index, -1)}
                      >
                        <ChevronUpIcon />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={t("columns.moveDownColumn", { name: column.name })}
                        disabled={index === columns.length - 1 || Boolean(pendingColumnId)}
                        pending={pendingColumnId === column.id && reorder.isPending}
                        pendingLabel={t("feedback.saving")}
                        onClick={() => move(index, 1)}
                      >
                        <ChevronDownIcon />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={t("columns.renameColumn", { name: column.name })}
                        title={t("columns.rename")}
                        onClick={(event) => {
                          dialogFocus.remember(event.currentTarget);
                          setRenaming(column);
                        }}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="destructive"
                        aria-label={t("columns.deleteColumn", { name: column.name })}
                        disabled={remove.isPending}
                        onClick={(event) => {
                          dialogFocus.remember(event.currentTarget);
                          setDeleteTarget(column);
                        }}
                      >
                        <Trash2Icon />
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>
        )}
        <ConfirmDialog
          finalFocus={dialogFocus.finalFocus}
          open={Boolean(deleteTarget)}
          onOpenChange={(open) => !open && setDeleteTarget(undefined)}
          title={t("columns.delete")}
          description={t("columns.deleteConfirm", { label: deleteTarget?.name })}
          cancelLabel={t("forms.cancel")}
          confirmLabel={t("columns.delete")}
          destructive
          pending={remove.isPending}
          pendingLabel={t("feedback.saving")}
          onConfirm={() => deleteTarget && remove.mutate({ path: { column_id: deleteTarget.id } })}
        />
        <RenameFieldDialog
          column={renaming}
          finalFocus={dialogFocus.finalFocus}
          onClose={() => setRenaming(undefined)}
          onRenamed={invalidate}
        />
      </AdminPage>
    </div>
  );
}

function CreateDialog({
  grade,
  subject,
  onCreated,
}: {
  grade: number;
  subject: Subject;
  onCreated: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const notifyDone = useNotifyDone();
  const [open, setOpen] = useState(false);
  const isSecondLanguage = subject !== "english";
  const scaleOnly = grade === 4 && isSecondLanguage;
  const allowText = subject !== "english" || grade < 5;
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: "",
      group: "",
      turkish_name: "",
      turkish_group: "",
      value_type: scaleOnly ? "scale3" : "score",
      owner_role: isSecondLanguage ? subject : "main",
      counts_in_average: false,
    },
  });
  const valueType = useWatch({ control: form.control, name: "value_type" });
  const effectiveType =
    scaleOnly && valueType === "score"
      ? "scale3"
      : !allowText && valueType === "text"
        ? "score"
        : valueType;
  // Mirrors backend prints_turkish: the primary English card prints every field in Turkish
  // too; the karne prints its ratings and notes in Turkish, while its scores only feed the average.
  const printsTurkish = subject === "english" ? grade < 5 : effectiveType !== "score";
  const create = useMutation({
    ...createColumnMutation(),
    onSuccess: (created) => {
      notifyDone(t("columns.created", { name: created.name }), created.action_id);
      void onCreated();
      setOpen(false);
      form.reset();
    },
  });
  const submit = form.handleSubmit((values) => {
    if (printsTurkish && !values.turkish_name) {
      form.setError("turkish_name", { type: "required" });
      return;
    }
    if (printsTurkish && values.group && !values.turkish_group) {
      form.setError("turkish_group", { type: "required" });
      return;
    }
    create.mutate({
      body: {
        grade_level: grade,
        subject,
        value_type: effectiveType,
        owner_role: values.owner_role,
        name: values.name,
        group: values.group || null,
        turkish_name: printsTurkish ? values.turkish_name : null,
        turkish_group: printsTurkish && values.group ? values.turkish_group : null,
        counts_in_average: !scaleOnly && values.counts_in_average,
      },
    });
  });
  const countsInAverage = useWatch({ control: form.control, name: "counts_in_average" });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        <PlusIcon />
        {t("columns.add")}
      </DialogTrigger>
      {/* Header and footer stay put while the fields scroll, so Cancel and Save remain
          visible on a short phone screen. */}
      <DialogContent className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base">{t("columns.add")}</DialogTitle>
        </DialogHeader>

        <div className="-mx-1 min-h-0 space-y-4 overflow-y-auto px-1 pb-1">
          {scaleOnly ? (
            <p className="text-sm text-muted-foreground">{t("grid.gradeFourScaleOnly")}</p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label={t("columns.name", { language: t(`subjects.${subject}`) })}
              error={form.formState.errors.name ? t("forms.required") : undefined}
            >
              {(id) => <Input id={id} {...form.register("name")} />}
            </Field>
            {printsTurkish ? (
              <Field
                label={t("columns.turkishName")}
                error={form.formState.errors.turkish_name ? t("forms.required") : undefined}
              >
                {(id) => <Input id={id} lang="tr" {...form.register("turkish_name")} />}
              </Field>
            ) : null}
            <Field label={t("columns.group")}>
              {(id) => <Input id={id} {...form.register("group")} />}
            </Field>
            {printsTurkish ? (
              <Field
                label={t("columns.turkishGroup")}
                error={form.formState.errors.turkish_group ? t("forms.required") : undefined}
              >
                {(id) => <Input id={id} lang="tr" {...form.register("turkish_group")} />}
              </Field>
            ) : null}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("columns.valueType")}>
              {(id) => (
                <NativeSelect id={id} {...form.register("value_type")}>
                  {!scaleOnly ? (
                    <option value="score">{t("columns.valueTypes.score")}</option>
                  ) : null}
                  <option value="scale3">{t("columns.valueTypes.scale3")}</option>
                  {allowText ? <option value="text">{t("columns.valueTypes.text")}</option> : null}
                </NativeSelect>
              )}
            </Field>
            <Field label={t("columns.ownerRole")}>
              {(id) => (
                <NativeSelect id={id} {...form.register("owner_role")}>
                  {(isSecondLanguage ? [subject] : ["main", "skills"]).map((role) => (
                    <option key={role} value={role}>
                      {t(`roles.${role}`)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          </div>

          <label className="flex items-center gap-2.5 text-sm">
            <Checkbox
              checked={!scaleOnly && countsInAverage}
              disabled={scaleOnly}
              onCheckedChange={(value) =>
                form.setValue("counts_in_average", value === true, { shouldDirty: true })
              }
            />
            {t("columns.countsInAverage")}
          </label>
        </div>

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>{t("forms.cancel")}</DialogClose>
          <Button onClick={submit} pending={create.isPending} pendingLabel={t("feedback.saving")}>
            {t("forms.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
