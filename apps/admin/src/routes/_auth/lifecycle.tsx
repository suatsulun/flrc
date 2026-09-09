import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { DownloadIcon, PlusIcon } from "lucide-react";
import { toast } from "sonner";
import {
  activateYearMutation,
  advanceSemesterMutation,
  closeYearMutation,
  createYearMutation,
  listYearsOptions,
  listYearsQueryKey,
  lockSemesterTwoMutation,
  reopenSemesterMutation,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";
import { ConfirmDialog } from "@flrc/ui/components/dialog";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { AdminPage } from "../../admin/AdminPage";

export const Route = createFileRoute("/_auth/lifecycle")({ component: LifecyclePage });

const YEAR_TONE = {
  setup: "warning",
  active: "success",
  archived: "neutral",
} as const;

function LifecyclePage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [archiveTarget, setArchiveTarget] = useState<{ id: number; label: string }>();
  const [auditDigest, setAuditDigest] = useState<string>();
  const [archiveConfirmation, setArchiveConfirmation] = useState("");
  const [auditPending, setAuditPending] = useState(false);
  const [reopenTarget, setReopenTarget] = useState<{ id: number; label: string }>();
  const [reopenConfirmation, setReopenConfirmation] = useState("");
  const { data: years = [], isPending: yearsPending } = useQuery(listYearsOptions());
  const refresh = () => queryClient.invalidateQueries({ queryKey: listYearsQueryKey() });
  const succeeded = () => {
    toast.success(t("feedback.actionSucceeded"));
    return refresh();
  };
  const create = useMutation({
    ...createYearMutation(),
    onSuccess: () => {
      setLabel("");
      void succeeded();
    },
  });
  const activate = useMutation({ ...activateYearMutation(), onSuccess: succeeded });
  const advance = useMutation({ ...advanceSemesterMutation(), onSuccess: succeeded });
  const lock = useMutation({ ...lockSemesterTwoMutation(), onSuccess: succeeded });
  const reopen = useMutation({
    ...reopenSemesterMutation(),
    onSuccess: () => {
      setReopenTarget(undefined);
      setReopenConfirmation("");
      void succeeded();
    },
  });
  const close = useMutation({
    ...closeYearMutation(),
    onSuccess: () => {
      setArchiveTarget(undefined);
      setAuditDigest(undefined);
      setArchiveConfirmation("");
      void succeeded();
    },
  });
  const transitionFailed = [
    create.error,
    activate.error,
    advance.error,
    lock.error,
    reopen.error,
    close.error,
  ].some(Boolean);
  const latestStandard = years
    .map((year) => year.label.match(/^(\d{4})-(\d{4})$/))
    .filter((match): match is RegExpMatchArray => Boolean(match))
    .sort((left, right) => Number(right[1]) - Number(left[1]))[0];
  const suggestedLabel = latestStandard
    ? `${latestStandard[2]}-${Number(latestStandard[2]) + 1}`
    : "2026-2027";

  async function downloadAudit() {
    if (!archiveTarget) return;
    setAuditPending(true);
    toast.loading(t("lifecycle.exportingAudit"), { id: "audit-export" });
    try {
      const response = await fetch(`/api/admin/years/${archiveTarget.id}/audit-export.csv`);
      if (!response.ok) throw new Error(`Audit export failed (${response.status})`);
      const digest = response.headers.get("x-audit-sha256");
      if (!digest) throw new Error("Audit digest is missing");
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `audit-${archiveTarget.label}.csv`;
      anchor.click();
      URL.revokeObjectURL(href);
      setAuditDigest(digest);
      toast.success(t("lifecycle.auditReady"), { id: "audit-export" });
    } catch {
      toast.error(t("feedback.actionFailed"), { id: "audit-export" });
    } finally {
      setAuditPending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ body: { label: label || suggestedLabel } });
  }

  const transitionPending =
    create.isPending ||
    activate.isPending ||
    advance.isPending ||
    lock.isPending ||
    reopen.isPending ||
    close.isPending ||
    auditPending;

  if (yearsPending) return <PageSkeleton />;

  return (
    <AdminPage title={t("lifecycle.title")} description={t("lifecycle.description")}>
      <div className="rounded-xl border border-success/25 bg-success-surface/55 px-4 py-3 text-sm">
        <p className="font-semibold">{t("lifecycle.automaticTitle")}</p>
        <p className="mt-0.5 text-muted-foreground">{t("lifecycle.automaticBody")}</p>
      </div>
      {transitionFailed ? (
        <p
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive-surface px-4 py-3 text-sm text-destructive"
        >
          {t("lifecycle.actionFailed")}
        </p>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>{t("lifecycle.create")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-wrap items-end gap-3" onSubmit={submit}>
            <Field label={t("lifecycle.yearLabel")} className="w-full max-w-xs">
              {(id) => (
                <Input
                  id={id}
                  required
                  placeholder={suggestedLabel}
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                />
              )}
            </Field>
            <Button pending={create.isPending} pendingLabel={t("lifecycle.creating")}>
              <PlusIcon />
              {t("lifecycle.create")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {years.map((year) => {
          const first = year.semesters.find((item) => item.number === 1);
          const second = year.semesters.find((item) => item.number === 2);
          const activeSemester = year.semesters
            .filter((item) => item.status === "open")
            .sort((left, right) => right.number - left.number)[0];
          const otherActiveYear = years.find(
            (item) => item.status === "active" && item.id !== year.id,
          );
          const activationReason = otherActiveYear
            ? t("lifecycle.finishActiveYear", { label: otherActiveYear.label })
            : year.missing_school_numbers > 0
              ? t("lifecycle.missingNumbers", { count: year.missing_school_numbers })
              : undefined;
          const actions = [
            year.status === "setup" && {
              key: "activate",
              label: t("lifecycle.activate"),
              variant: "default" as const,
              disabled: Boolean(activationReason),
              pending: activate.isPending && activate.variables?.path.year_id === year.id,
              run: () => activate.mutate({ path: { year_id: year.id } }),
            },
            activeSemester?.number === 1 && {
              key: "advance",
              label: t("lifecycle.advance"),
              variant: "default" as const,
              disabled: false,
              pending: advance.isPending && advance.variables?.path.year_id === year.id,
              run: () => advance.mutate({ path: { year_id: year.id } }),
            },
            activeSemester?.number === 2 && {
              key: "lock",
              label: t("lifecycle.lockSecond"),
              variant: "default" as const,
              disabled: false,
              pending: lock.isPending && lock.variables?.path.year_id === year.id,
              run: () => lock.mutate({ path: { year_id: year.id } }),
            },
            year.status === "active" && {
              key: "reopen",
              label: t("lifecycle.reopen"),
              variant: "destructive" as const,
              disabled: false,
              pending: reopen.isPending && reopen.variables?.path.year_id === year.id,
              run: () => setReopenTarget({ id: year.id, label: year.label }),
            },
            year.status === "active" &&
              year.semesters.every((item) => item.status === "locked") && {
                key: "close",
                label: t("lifecycle.close"),
                variant: "destructive" as const,
                disabled: false,
                pending: close.isPending && close.variables?.path.year_id === year.id,
                run: () => setArchiveTarget({ id: year.id, label: year.label }),
              },
          ].filter(Boolean) as Array<{
            key: string;
            label: string;
            variant: "default" | "destructive";
            disabled: boolean;
            pending: boolean;
            run: () => void;
          }>;

          return (
            <Card
              key={year.id}
              data-testid="lifecycle-year"
              data-year-status={year.status}
              data-missing-school-numbers={year.missing_school_numbers}
            >
              <CardHeader>
                <CardTitle className="text-base">{year.label}</CardTitle>
                <Badge tone={YEAR_TONE[year.status as keyof typeof YEAR_TONE] ?? "neutral"}>
                  {t(`lifecycle.${year.status}`)}
                </Badge>
              </CardHeader>
              <CardContent className="space-y-3">
                {year.status === "setup" ? (
                  <p className="text-xs text-muted-foreground">
                    {activationReason ?? t("lifecycle.setupReady")}
                  </p>
                ) : null}
                <dl className="grid gap-2 sm:grid-cols-2">
                  {[first, second].map((semester, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between gap-2 rounded-lg bg-muted/60 px-3 py-2"
                    >
                      <dt className="text-sm text-muted-foreground">
                        {t("lifecycle.semester", { number: index + 1 })}
                      </dt>
                      <dd>
                        <Badge tone={semester?.id === activeSemester?.id ? "success" : "neutral"}>
                          {semester?.id === activeSemester?.id
                            ? t("lifecycle.activeSemester")
                            : t("lifecycle.locked")}
                        </Badge>
                      </dd>
                    </div>
                  ))}
                </dl>

                {actions.length ? (
                  <div className="flex flex-wrap gap-2">
                    {actions.map((action) => (
                      <Button
                        key={action.key}
                        size="sm"
                        variant={action.variant}
                        disabled={action.disabled || (transitionPending && !action.pending)}
                        pending={action.pending}
                        pendingLabel={t("feedback.working")}
                        title={action.disabled ? activationReason : undefined}
                        onClick={action.run}
                      >
                        {action.label}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <ConfirmDialog
        open={Boolean(reopenTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setReopenTarget(undefined);
            setReopenConfirmation("");
          }
        }}
        title={t("lifecycle.reopen")}
        description={
          reopenTarget ? t("lifecycle.reopenConfirm", { label: reopenTarget.label }) : undefined
        }
        cancelLabel={t("forms.cancel")}
        confirmLabel={t("lifecycle.reopen")}
        destructive
        pending={reopen.isPending}
        pendingLabel={t("feedback.working")}
        confirmDisabled={!reopenTarget || reopenConfirmation !== reopenTarget.label}
        onConfirm={() => {
          if (!reopenTarget || reopenConfirmation !== reopenTarget.label) return;
          reopen.mutate({
            path: { year_id: reopenTarget.id },
            body: { number: 1, confirm_label: reopenConfirmation },
          });
        }}
      >
        <Input
          autoFocus
          value={reopenConfirmation}
          onChange={(event) => setReopenConfirmation(event.target.value)}
          placeholder={reopenTarget?.label}
          aria-label={t("lifecycle.confirmationLabel")}
        />
      </ConfirmDialog>

      <ConfirmDialog
        open={Boolean(archiveTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setArchiveTarget(undefined);
            setAuditDigest(undefined);
            setArchiveConfirmation("");
          }
        }}
        title={t("lifecycle.close")}
        description={
          auditDigest
            ? t("lifecycle.closeConfirm", { label: archiveTarget?.label })
            : t("lifecycle.archiveSafety")
        }
        cancelLabel={t("forms.cancel")}
        confirmLabel={auditDigest ? t("lifecycle.close") : t("lifecycle.downloadAudit")}
        destructive={Boolean(auditDigest)}
        pending={auditPending || close.isPending}
        pendingLabel={t("feedback.working")}
        confirmDisabled={Boolean(auditDigest) && archiveConfirmation !== archiveTarget?.label}
        onConfirm={() => {
          if (!archiveTarget) return;
          if (!auditDigest) {
            void downloadAudit();
            return;
          }
          if (archiveConfirmation !== archiveTarget.label) return;
          close.mutate({
            path: { year_id: archiveTarget.id },
            body: { confirm_label: archiveConfirmation, audit_sha256: auditDigest },
          });
        }}
      >
        {auditDigest ? (
          <div className="space-y-3">
            <p className="flex items-center gap-2 rounded-lg bg-success-surface px-3 py-2 text-sm text-success">
              <DownloadIcon className="size-4" />
              {t("lifecycle.storedAudit")}
            </p>
            <Input
              autoFocus
              value={archiveConfirmation}
              onChange={(event) => setArchiveConfirmation(event.target.value)}
              placeholder={archiveTarget?.label}
              aria-label={t("lifecycle.confirmationLabel")}
            />
          </div>
        ) : null}
      </ConfirmDialog>
    </AdminPage>
  );
}
