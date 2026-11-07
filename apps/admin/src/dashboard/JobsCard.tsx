import { listJobsOptions } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { buttonVariants } from "@flrc/ui/components/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { useQuery } from "@tanstack/react-query";
import { DownloadIcon, Loader2Icon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { parseUtc } from "./format";

const JOB_LIMIT = 8;
const POLL_MS = 3000;
const STATUS_TONE = {
  queued: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
} as const;

/** Background report and export jobs: progress while running, the file while it is kept. */
export function JobsCard() {
  const { t, i18n } = useTranslation();
  const {
    data: jobs = [],
    isError,
    // Expiry is judged at fetch time; a list refetches on focus and while jobs run.
    dataUpdatedAt,
  } = useQuery({
    ...listJobsOptions({ query: { limit: JOB_LIMIT } }),
    refetchInterval: (query) =>
      query.state.data?.some((job) => job.status === "queued" || job.status === "running")
        ? POLL_MS
        : false,
  });

  return (
    <Card>
      <CardHeader>
        <div className="min-w-0">
          <CardTitle>{t("adminDashboard.jobs.title")}</CardTitle>
          <CardDescription>{t("adminDashboard.jobs.description")}</CardDescription>
        </div>
      </CardHeader>
      {isError ? (
        <p className="border-t border-border px-5 py-6 text-sm text-muted-foreground">
          {t("errors.load")}
        </p>
      ) : jobs.length === 0 ? (
        <p className="border-t border-border px-5 py-6 text-sm text-muted-foreground">
          {t("adminDashboard.jobs.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {jobs.map((job) => {
            const active = job.status === "queued" || job.status === "running";
            const expiresAt = job.output_expires_at ? parseUtc(job.output_expires_at) : undefined;
            const downloadable =
              job.status === "succeeded" &&
              expiresAt !== undefined &&
              expiresAt.getTime() > dataUpdatedAt;
            return (
              <li key={job.id} className="flex items-center gap-3 px-5 py-2.5">
                <div className="min-w-0 flex-1">
                  <p
                    className="truncate text-sm font-medium"
                    title={job.output_filename ?? undefined}
                  >
                    {job.output_filename ??
                      t(`reports.kinds.${job.kind}`, { defaultValue: job.kind })}
                  </p>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                    <Badge tone={STATUS_TONE[job.status as keyof typeof STATUS_TONE] ?? "neutral"}>
                      {active ? <Loader2Icon className="animate-spin" /> : null}
                      {t(`reports.status.${job.status}`, {
                        progress: job.progress,
                        total: job.total,
                      })}
                    </Badge>
                    {job.status === "succeeded" && expiresAt ? (
                      <span>
                        {downloadable
                          ? t("adminDashboard.jobs.expires", {
                              time: expiresAt.toLocaleString(i18n.language, {
                                dateStyle: "short",
                                timeStyle: "short",
                              }),
                            })
                          : t("adminDashboard.jobs.expired")}
                      </span>
                    ) : null}
                  </p>
                  {active && job.total > 0 ? (
                    <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-muted">
                      <span
                        className="block h-full rounded-full bg-primary transition-[width]"
                        style={{ width: `${Math.min((job.progress / job.total) * 100, 100)}%` }}
                      />
                    </span>
                  ) : null}
                </div>
                {downloadable ? (
                  <a
                    href={`/api/jobs/${job.id}/download`}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    <DownloadIcon />
                    {t("reports.download")}
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
