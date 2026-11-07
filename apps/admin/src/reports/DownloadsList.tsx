import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { DownloadIcon, FileArchiveIcon, FileSpreadsheetIcon, FileTextIcon } from "lucide-react";
import { toast } from "sonner";
import { listJobsOptions, type JobOut } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { jobFailureMessage } from "./report-errors";

/** A job that is still waiting or running: the list polls and shows its progress. */
const isActive = (status: string) => status === "queued" || status === "running";
const POLL_MS = 2000;
const STATUS_TONE = {
  queued: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
} as const;

/** Job times are naive UTC on the server; read them as UTC, not as local time. */
function serverTime(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

function JobIcon({ job }: { job: JobOut }) {
  const name = job.output_filename ?? "";
  const Icon =
    job.kind === "year_export"
      ? FileSpreadsheetIcon
      : name.endsWith(".zip")
        ? FileArchiveIcon
        : FileTextIcon;
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
      <Icon className="size-4" />
    </span>
  );
}

function DownloadButton({ jobId, label }: { jobId: number; label: string }) {
  return (
    <Button
      size="sm"
      variant="outline"
      render={<a href={`/api/jobs/${jobId}/download`} download />}
    >
      <DownloadIcon />
      {label}
    </Button>
  );
}

/**
 * Report and export jobs with live progress, kept server-side for 24 hours (ADR-024, ADR-077):
 * the list survives reloads and polls only while a job is waiting or running. A set too large
 * for one file lists its numbered parts under the request, each with its own download.
 */
export function DownloadsList() {
  const { t, i18n } = useTranslation();
  const {
    data: jobs = [],
    isError,
    dataUpdatedAt,
  } = useQuery({
    ...listJobsOptions(),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((job) => isActive(job.status)) ? POLL_MS : false,
  });
  const seen = useRef(new Map<number, string>());
  const listed = new Set(jobs.map((job) => job.id));
  const partsOf = new Map<number, JobOut[]>();
  for (const job of [...jobs].sort((a, b) => (a.part ?? 0) - (b.part ?? 0))) {
    if (job.parent_id !== null && listed.has(job.parent_id)) {
      partsOf.set(job.parent_id, [...(partsOf.get(job.parent_id) ?? []), job]);
    }
  }
  const requests = jobs.filter((job) => job.parent_id === null || !listed.has(job.parent_id));

  // A request finishing while the page is open says so; history loaded on arrival stays quiet.
  useEffect(() => {
    for (const job of jobs) {
      if (job.parent_id !== null) continue;
      const before = seen.current.get(job.id);
      seen.current.set(job.id, job.status);
      if (!before || !isActive(before) || isActive(job.status)) continue;
      const name = job.output_filename ?? t(`reports.kinds.${job.kind}`);
      if (job.status === "succeeded") {
        toast.success(t("reports.downloads.ready", { name }));
      } else {
        toast.error(
          t("reports.downloads.failedNamed", {
            name,
            reason: jobFailureMessage(t, job.error_code),
          }),
        );
      }
    }
  }, [jobs, t]);

  const dateTime = new Intl.DateTimeFormat(i18n.language, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  const megabytes = new Intl.NumberFormat(i18n.language, {
    style: "unit",
    unit: "megabyte",
    maximumFractionDigits: 1,
  });
  const kilobytes = new Intl.NumberFormat(i18n.language, {
    style: "unit",
    unit: "kilobyte",
    maximumFractionDigits: 0,
  });
  const size = (bytes: number) =>
    bytes >= 1_000_000 ? megabytes.format(bytes / 1_000_000) : kilobytes.format(bytes / 1_000);

  return (
    <Card aria-live="polite">
      <CardHeader>
        <div>
          <CardTitle>{t("reports.downloads.title")}</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">{t("reports.downloads.description")}</p>
        </div>
      </CardHeader>
      <CardBody>
        {isError ? (
          <p className="px-5 py-8 text-center text-sm text-destructive">{t("errors.load")}</p>
        ) : requests.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">
            {t("reports.downloads.empty")}
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {requests.map((job) => {
              const active = isActive(job.status);
              const expires = job.output_expires_at ? serverTime(job.output_expires_at) : null;
              // Judged at the list's last refresh (polling, focus, a new job), not on each render.
              const ready =
                job.status === "succeeded" && expires !== null && expires.getTime() > dataUpdatedAt;
              const expired = job.status === "succeeded" && !ready;
              const parts = ready ? (partsOf.get(job.id) ?? []) : [];
              const name = job.output_filename ?? t(`reports.kinds.${job.kind}`);
              const details = [dateTime.format(serverTime(job.created_at))];
              if (parts.length > 0) {
                details.push(t("reports.downloads.parts", { count: parts.length }));
              }
              if (ready && job.output_size !== null) details.push(size(job.output_size));
              if (ready && expires) {
                details.push(t("reports.downloads.expires", { time: dateTime.format(expires) }));
              }
              if (expired) details.push(t("reports.downloads.expired"));
              return (
                <li key={job.id} className="px-5 py-3">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 items-start gap-3">
                      <JobIcon job={job} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium break-words">{name}</p>
                        <p className="tabular text-xs text-muted-foreground">
                          {details.join(" · ")}
                        </p>
                        {active ? (
                          <div className="mt-2 grid gap-1">
                            <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
                              <span
                                className="block h-full rounded-full bg-primary transition-[width]"
                                style={{
                                  width: `${Math.min((job.progress / Math.max(job.total, 1)) * 100, 100)}%`,
                                }}
                              />
                            </span>
                            <span className="tabular text-xs text-muted-foreground">
                              {job.kind === "report_set"
                                ? t("reports.downloads.classProgress", {
                                    progress: job.progress,
                                    total: job.total,
                                  })
                                : t("reports.downloads.stepProgress", {
                                    progress: job.progress,
                                    total: job.total,
                                  })}
                            </span>
                          </div>
                        ) : null}
                        {job.status === "failed" ? (
                          <p className="mt-1 text-xs text-destructive">
                            {jobFailureMessage(t, job.error_code)}
                          </p>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 self-end sm:self-auto">
                      <Badge
                        tone={STATUS_TONE[job.status as keyof typeof STATUS_TONE] ?? "neutral"}
                      >
                        {t(`reports.status.${job.status}`)}
                      </Badge>
                      {ready && parts.length === 0 ? (
                        <DownloadButton jobId={job.id} label={t("reports.download")} />
                      ) : null}
                    </div>
                  </div>
                  {parts.length > 0 ? (
                    <ul
                      aria-label={t("reports.downloads.partsOf", { name })}
                      className="mt-2 grid gap-1.5 border-l-2 border-border pl-4 sm:ml-11"
                    >
                      {parts.map((part) => (
                        <li
                          key={part.id}
                          className="flex flex-wrap items-center justify-between gap-2 text-sm"
                        >
                          <span className="min-w-0 break-words">
                            {part.output_filename}
                            {part.output_size !== null ? (
                              <span className="tabular ml-2 text-xs text-muted-foreground">
                                {size(part.output_size)}
                              </span>
                            ) : null}
                          </span>
                          <DownloadButton jobId={part.id} label={t("reports.download")} />
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
