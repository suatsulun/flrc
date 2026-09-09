import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { DownloadIcon, FileTextIcon, ExternalLinkIcon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import {
  coordinatorOverviewOptions,
  createYearExportJobMutation,
  getJobOptions,
  listJobsOptions,
  listJobsQueryKey,
  listYearsOptions,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardContent, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Field } from "@flrc/ui/components/field";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { Segmented } from "@flrc/ui/components/segmented";
import { AdminPage } from "../../admin/AdminPage";

const JOB_KEY = "flrc-active-export-job";
type ReportKind = "english_elementary" | "english_middle" | "german_karne" | "french_karne";
type Locale = "tr" | "en" | "de" | "fr";
const REPORT_KINDS: ReportKind[] = [
  "english_elementary",
  "english_middle",
  "german_karne",
  "french_karne",
];
const LOCALES = [
  { value: "tr", label: "TR", title: "Türkçe" },
  { value: "en", label: "EN", title: "English" },
  { value: "de", label: "DE", title: "Deutsch" },
  { value: "fr", label: "FR", title: "Français" },
] as const;

export const Route = createFileRoute("/_auth/reports")({ component: ReportsPage });

const STATUS_TONE = {
  queued: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
} as const;

function ReportsPage() {
  const { user } = Route.useRouteContext();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: overview, isPending: overviewPending } = useQuery(coordinatorOverviewOptions());
  const { data: years = [], isPending: yearsPending } = useQuery({
    ...listYearsOptions(),
    enabled: user.is_admin,
  });
  const { data: jobs = [], isPending: jobsPending } = useQuery(listJobsOptions());
  const [yearId, setYearId] = useState<number>();
  const [locale, setLocale] = useState<Locale>("tr");
  const [generatingKind, setGeneratingKind] = useState<ReportKind>();
  const [jobId, setJobId] = useState<number | null>(
    () => Number(sessionStorage.getItem(JOB_KEY)) || null,
  );
  const activeYearId = yearId ?? years[0]?.id;

  const reportUrl = (kind: ReportKind) =>
    overview?.semester_id
      ? `/api/reports/pdf?${new URLSearchParams({
          semester_id: String(overview.semester_id),
          kind,
          locale,
        })}`
      : null;

  const refreshHistory = () => queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
  const remember = (id: number) => {
    setJobId(id);
    sessionStorage.setItem(JOB_KEY, String(id));
    void refreshHistory();
  };
  const createExport = useMutation({
    ...createYearExportJobMutation(),
    onMutate: () => toast.loading(t("reports.exportStarting"), { id: "year-export" }),
    onSuccess: (job) => {
      remember(job.id);
      toast.success(t("reports.exportQueued"), { id: "year-export" });
    },
    onError: () => toast.dismiss("year-export"),
  });
  const jobOptions = getJobOptions({ path: { job_id: jobId ?? 0 } });
  const { data: activeJob } = useQuery({
    ...jobOptions,
    enabled: jobId !== null,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "") ? 2000 : false,
  });
  const lastJobState = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!activeJob) return;
    const state = `${activeJob.id}:${activeJob.status}:${activeJob.progress}`;
    if (lastJobState.current === state) return;
    lastJobState.current = state;
    const toastId = `job-${activeJob.id}`;
    if (["queued", "running"].includes(activeJob.status)) {
      toast.loading(
        t(`reports.status.${activeJob.status}`, {
          progress: activeJob.progress,
          total: activeJob.total,
        }),
        { id: toastId },
      );
    } else if (activeJob.status === "succeeded") {
      toast.success(t("reports.exportReady"), { id: toastId });
      void queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
    } else if (activeJob.status === "failed") {
      toast.error(t("reports.failedCode", { code: activeJob.error_code, id: activeJob.id }), {
        id: toastId,
      });
      void queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
    }
  }, [activeJob, queryClient, t]);

  async function openReport(kind: ReportKind) {
    const url = reportUrl(kind);
    if (!url || generatingKind) return;

    setGeneratingKind(kind);
    const toastId = `pdf-${kind}`;
    toast.loading(t("reports.generatingPdf"), { id: toastId });
    const reportTab = window.open("", "_blank");
    if (reportTab) {
      reportTab.document.title = t("reports.generatingPdf");
      reportTab.document.body.style.cssText =
        "margin:0;display:grid;place-items:center;min-height:100vh;font:16px system-ui;background:#eef1ec;color:#25312c";
      reportTab.document.body.textContent = t("reports.generatingPdf");
    }

    try {
      const response = await fetch(url, { headers: { Accept: "application/pdf" } });
      if (!response.ok) throw new Error(`PDF generation failed (${response.status})`);
      const blobUrl = URL.createObjectURL(await response.blob());
      if (reportTab) {
        reportTab.location.href = blobUrl;
      } else {
        const anchor = document.createElement("a");
        anchor.href = blobUrl;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        anchor.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 300_000);
      toast.success(t("reports.pdfReady"), { id: toastId });
    } catch {
      reportTab?.close();
      toast.error(t("reports.pdfFailed"), { id: toastId });
    } finally {
      setGeneratingKind(undefined);
    }
  }

  if (overviewPending || jobsPending || (user.is_admin && yearsPending)) {
    return <PageSkeleton />;
  }

  return (
    <AdminPage
      title={t("reports.title")}
      description={t("reports.description")}
      actions={
        <Field label={t("reports.languageLabel")}>
          {() => (
            <Segmented
              ariaLabel={t("reports.languageLabel")}
              options={LOCALES}
              value={locale}
              onChange={setLocale}
              size="sm"
            />
          )}
        </Field>
      }
    >
      <div className="grid gap-3 md:grid-cols-2">
        {REPORT_KINDS.map((kind) => {
          const url = reportUrl(kind);
          return (
            <Card key={kind} className="flex flex-col">
              <CardContent className="flex flex-1 flex-col">
                <div className="flex items-start justify-between gap-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                    <FileTextIcon className="size-4.5" />
                  </span>
                  <Badge tone="outline">{t(`reports.setScopes.${kind}`)}</Badge>
                </div>
                <h3 className="font-heading mt-3 font-semibold tracking-tight">
                  {t(`reports.kinds.${kind}`)}
                </h3>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {t(`reports.setDescriptions.${kind}`)}
                </p>
                <Button
                  className="mt-4 self-start"
                  size="sm"
                  disabled={!url || Boolean(generatingKind)}
                  pending={generatingKind === kind}
                  pendingLabel={t("reports.generatingPdf")}
                  onClick={() => void openReport(kind)}
                >
                  <ExternalLinkIcon />
                  {t("reports.openPdf")}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {user.is_admin ? (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("reports.yearExport")}</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">{t("reports.exportDescription")}</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <Field label={t("reports.yearLabel")}>
                {(id) => (
                  <NativeSelect
                    id={id}
                    className="w-40"
                    value={activeYearId ?? ""}
                    onChange={(event) => setYearId(Number(event.target.value))}
                  >
                    {years.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Button
                variant="outline"
                disabled={!activeYearId}
                pending={createExport.isPending}
                pendingLabel={t("reports.exporting")}
                onClick={() =>
                  activeYearId && createExport.mutate({ path: { year_id: activeYearId } })
                }
              >
                {t("reports.export")}
              </Button>
            </div>
          </CardHeader>
        </Card>
      ) : null}

      {activeJob ? (
        <Card aria-live="polite">
          <CardHeader>
            <div>
              <CardTitle>{t("reports.activeExport")}</CardTitle>
              <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                {["queued", "running"].includes(activeJob.status) ? (
                  <Loader2Icon className="size-3.5 animate-spin" />
                ) : null}
                {t(`reports.status.${activeJob.status}`, {
                  progress: activeJob.progress,
                  total: activeJob.total,
                })}
              </p>
            </div>
            {activeJob.status === "succeeded" ? (
              <Button variant="outline" render={<a href={`/api/jobs/${activeJob.id}/download`} />}>
                <DownloadIcon />
                {t("reports.download")}
              </Button>
            ) : null}
          </CardHeader>
          {["queued", "running"].includes(activeJob.status) ? (
            <CardContent>
              <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
                <span
                  className="block h-full rounded-full bg-primary transition-[width]"
                  style={{
                    width: `${Math.min((activeJob.progress / Math.max(activeJob.total, 1)) * 100, 100)}%`,
                  }}
                />
              </span>
            </CardContent>
          ) : null}
          {activeJob.status === "failed" ? (
            <CardContent>
              <p className="text-sm text-destructive">
                {t("reports.failedCode", { code: activeJob.error_code, id: activeJob.id })}
              </p>
            </CardContent>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{t("reports.history")}</CardTitle>
        </CardHeader>
        <CardBody>
          {jobs.length === 0 ? (
            <p className="px-5 py-8 text-center text-sm text-muted-foreground">
              {t("reports.noHistory")}
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {jobs.map((job) => (
                <li key={job.id} className="flex items-center justify-between gap-3 px-5 py-2.5">
                  <button
                    type="button"
                    className="truncate text-sm font-medium text-primary-strong transition-colors hover:underline"
                    onClick={() => remember(job.id)}
                  >
                    <span className="tabular text-muted-foreground">#{job.id}</span>{" "}
                    {t(`reports.kinds.${job.kind}`)}
                  </button>
                  <Badge tone={STATUS_TONE[job.status as keyof typeof STATUS_TONE] ?? "neutral"}>
                    {t(`reports.status.${job.status}`, {
                      progress: job.progress,
                      total: job.total,
                    })}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </AdminPage>
  );
}
