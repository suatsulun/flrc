import type { TFunction } from "i18next";
import { FileRequestError } from "@flrc/ui/lib/file-delivery";

/** A specific message for a failed download or job request, including how long to wait. */
export function reportRequestMessage(t: TFunction, error: unknown): string {
  if (!(error instanceof FileRequestError)) return t("reports.errors.network");
  if (error.rateLimited) {
    return error.retryAfterSeconds
      ? t("reports.errors.rateLimitedWait", { seconds: error.retryAfterSeconds })
      : t("reports.errors.rateLimited");
  }
  switch (error.code) {
    case "empty_report_set":
      return t("reports.errors.empty");
    case "student_not_in_report_set":
    case "class_not_in_report_set":
    case "class_not_in_semester":
    case "unknown_class":
      return t("reports.errors.selectionChanged");
    case "demo_report_class_required":
      return t("reports.errors.demoJobs");
    case "output_expired":
      return t("reports.errors.expired");
    default:
      return t("reports.pdfFailed");
  }
}

/** Why a background job failed, from its stored error code. */
export function jobFailureMessage(t: TFunction, code: string | null): string {
  switch (code) {
    case "empty_report_set":
      return t("reports.errors.empty");
    case "report_page_mapping":
      return t("reports.errors.pageMapping");
    case "report_output_too_large":
      return t("reports.errors.tooLarge");
    case "report_job_retired":
      return t("reports.errors.retired");
    default:
      return t("reports.errors.jobFailed");
  }
}
