import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ChevronDownIcon, ChevronUpIcon, PlusIcon, Trash2Icon } from "lucide-react";
import {
  createColumnMutation,
  deleteColumnMutation,
  listColumnsOptions,
  listColumnsQueryKey,
  reorderColumnsMutation,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody } from "@flrc/ui/components/card";
import { Checkbox } from "@flrc/ui/components/checkbox";
import {
  Dialog,
  DialogContent,
  ConfirmDialog,
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

const GRADES = [1, 2, 3, 4, 5, 6, 7, 8];
const SUBJECTS = ["english", "german", "french"] as const;
const LOCALES = ["tr", "en", "de", "fr"] as const;
type Subject = (typeof SUBJECTS)[number];

export const Route = createFileRoute("/_auth/columns")({
  validateSearch: (s): { grade: number; subject: Subject } => ({
    grade: GRADES.includes(Number(s.grade)) ? Number(s.grade) : 5,
    subject: SUBJECTS.includes(s.subject as Subject) ? (s.subject as Subject) : "english",
  }),
  component: ColumnsPage,
});

const formSchema = z.object({
  label_tr: z.string().min(1),
  label_en: z.string(),
  label_de: z.string(),
  label_fr: z.string(),
  group_tr: z.string(),
  group_en: z.string(),
  group_de: z.string(),
  group_fr: z.string(),
  value_type: z.enum(["score", "scale3", "text"]),
  owner_role: z.enum(["main", "skills", "german", "french"]),
  counts_in_average: z.boolean(),
});
type FormValues = z.infer<typeof formSchema>;

function ColumnsPage() {
  const { grade, subject } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = { grade_level: grade, subject };
  const listKey = listColumnsQueryKey({ query });
  const [pendingColumnId, setPendingColumnId] = useState<number>();
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; label: string }>();
  const { data: columns = [], isPending: columnsPending } = useQuery(listColumnsOptions({ query }));
  const invalidate = () => queryClient.invalidateQueries({ queryKey: listKey });

  const reorder = useMutation({
    ...reorderColumnsMutation(),
    onSuccess: () => {
      toast.success(t("feedback.saved"));
      void invalidate();
    },
    onSettled: () => setPendingColumnId(undefined),
  });
  const remove = useMutation({
    ...deleteColumnMutation(),
    onSuccess: (result) => {
      toast(result.disabled ? t("columns.disabledInfo") : t("columns.deletedInfo"));
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
    reorder.mutate({ body: { ordered_ids: ids } });
  };

  if (columnsPending) return <PageSkeleton />;

  return (
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
                {t("dashboard.grade", { grade: item })}
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
          <CreateDialog
            key={`${grade}-${subject}`}
            grade={grade}
            subject={subject}
            onCreated={invalidate}
          />
        </>
      }
    >
      {columns.length === 0 ? (
        <EmptyState title={t("columns.empty")} description={t("columns.emptyBody")} />
      ) : (
        <Card className="max-w-3xl">
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
                    <span className="block truncate text-sm font-medium">{column.labels.tr}</span>
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
                      aria-label={t("columns.moveUp")}
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
                      aria-label={t("columns.moveDown")}
                      disabled={index === columns.length - 1 || Boolean(pendingColumnId)}
                      pending={pendingColumnId === column.id && reorder.isPending}
                      pendingLabel={t("feedback.saving")}
                      onClick={() => move(index, 1)}
                    >
                      <ChevronDownIcon />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="destructive"
                      aria-label={t("columns.delete")}
                      disabled={remove.isPending}
                      onClick={() => setDeleteTarget({ id: column.id, label: column.labels.tr })}
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
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setDeleteTarget(undefined)}
        title={t("columns.delete")}
        description={t("columns.deleteConfirm", { label: deleteTarget?.label })}
        cancelLabel={t("forms.cancel")}
        confirmLabel={t("columns.delete")}
        destructive
        pending={remove.isPending}
        pendingLabel={t("feedback.saving")}
        onConfirm={() => deleteTarget && remove.mutate({ path: { column_id: deleteTarget.id } })}
      />
    </AdminPage>
  );
}

function CreateDialog({
  grade,
  subject,
  onCreated,
}: {
  grade: number;
  subject: Subject;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const isSecondLanguage = subject !== "english";
  const scaleOnly = grade === 4 && isSecondLanguage;
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      label_tr: "",
      label_en: "",
      label_de: "",
      label_fr: "",
      group_tr: "",
      group_en: "",
      group_de: "",
      group_fr: "",
      value_type: scaleOnly ? "scale3" : "score",
      owner_role: isSecondLanguage ? subject : "main",
      counts_in_average: false,
    },
  });
  const create = useMutation({
    ...createColumnMutation(),
    onSuccess: () => {
      onCreated();
      setOpen(false);
      form.reset();
    },
  });
  const submit = form.handleSubmit((values) => {
    const labels = {
      tr: values.label_tr,
      en: values.label_en,
      de: values.label_de,
      fr: values.label_fr,
    };
    const groupLabels = {
      tr: values.group_tr,
      en: values.group_en,
      de: values.group_de,
      fr: values.group_fr,
    };
    create.mutate({
      body: {
        grade_level: grade,
        subject,
        value_type: scaleOnly && values.value_type === "score" ? "scale3" : values.value_type,
        owner_role: values.owner_role,
        labels,
        group_labels: Object.values(groupLabels).some(Boolean) ? groupLabels : null,
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
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base">{t("columns.add")}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {scaleOnly ? (
            <p className="text-sm text-muted-foreground">{t("grid.gradeFourScaleOnly")}</p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            {LOCALES.map((locale) => (
              <Field
                key={locale}
                label={t("columns.labelLocale", { locale: locale.toUpperCase() })}
                error={
                  locale === "tr" && form.formState.errors.label_tr
                    ? t("forms.required")
                    : undefined
                }
              >
                {(id) => <Input id={id} {...form.register(`label_${locale}`)} />}
              </Field>
            ))}
          </div>

          <details className="rounded-lg border border-border px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium">
              {t("columns.groupLabels")}
            </summary>
            <div className="mt-3 grid gap-3 pb-1 sm:grid-cols-2">
              {LOCALES.map((locale) => (
                <Field key={locale} label={locale.toUpperCase()}>
                  {(id) => <Input id={id} {...form.register(`group_${locale}`)} />}
                </Field>
              ))}
            </div>
          </details>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("columns.valueType")}>
              {(id) => (
                <NativeSelect id={id} {...form.register("value_type")}>
                  {!scaleOnly ? (
                    <option value="score">{t("columns.valueTypes.score")}</option>
                  ) : null}
                  <option value="scale3">{t("columns.valueTypes.scale3")}</option>
                  <option value="text">{t("columns.valueTypes.text")}</option>
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

          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("forms.cancel")}
            </Button>
            <Button onClick={submit} pending={create.isPending} pendingLabel={t("feedback.saving")}>
              {t("forms.save")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
