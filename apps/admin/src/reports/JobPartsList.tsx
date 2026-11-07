import { useTranslation } from "react-i18next";
import { DownloadIcon } from "lucide-react";
import type { JobOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { cn } from "@flrc/ui/lib/utils";
import { formatBytes } from "./report-requests";

/** A job's file as a Download button; the server names the file. */
export function JobDownloadButton({ jobId }: { jobId: number }) {
  const { t } = useTranslation();
  return (
    <Button
      size="sm"
      variant="outline"
      render={<a href={`/api/jobs/${jobId}/download`} download />}
    >
      <DownloadIcon />
      {t("reports.download")}
    </Button>
  );
}

/** The numbered parts of a set too large for one file, each with its own download. */
export function JobPartsList({
  name,
  parts,
  className,
}: {
  name: string;
  parts: JobOut[];
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  return (
    <ul
      aria-label={t("reports.downloads.partsOf", { name })}
      className={cn("grid gap-1.5 border-l-2 border-border pl-4", className)}
    >
      {parts.map((part) => (
        <li key={part.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="min-w-0 break-words">
            {part.output_filename}
            {part.output_size !== null ? (
              <span className="tabular ml-2 text-xs text-muted-foreground">
                {formatBytes(part.output_size, i18n.language)}
              </span>
            ) : null}
          </span>
          <JobDownloadButton jobId={part.id} />
        </li>
      ))}
    </ul>
  );
}
