import type { TFunction } from "i18next";
import {
  createReportJob,
  createYearExportJob,
  type JobOut,
  type ReportJobIn,
  type RosterClass,
} from "@flrc/api-client";
import { FileRequestError } from "@flrc/ui/lib/file-delivery";

export type ReportKind = ReportJobIn["kind"];
export type ReportFormat = ReportJobIn["format"];
export type ReportLocale = NonNullable<ReportJobIn["locale"]>;

export const REPORT_KINDS: ReportKind[] = [
  "english_elementary",
  "english_middle",
  "german_karne",
  "french_karne",
];

/** The three delivery formats, in the order the controls offer them. */
export function reportFormatOptions(t: TFunction): { value: ReportFormat; label: string }[] {
  return [
    { value: "combined", label: t("reports.formats.combined") },
    { value: "per_class", label: t("reports.formats.per_class") },
    { value: "per_student", label: t("reports.formats.per_student") },
  ];
}

/** What a direct (instant) download covers: one whole class, or students of one class. */
export type DirectScope = { classId: number } | { studentIds: number[] };

/** What a background job covers; both lists empty means every eligible class. */
export type JobScope = { classIds: number[]; studentIds: number[] };

export function reportPdfUrl(
  semesterId: number,
  kind: ReportKind,
  locale: ReportLocale,
  scope: DirectScope,
): string {
  const query = new URLSearchParams({ semester_id: String(semesterId), kind, locale });
  if ("classId" in scope) query.set("class_id", String(scope.classId));
  else for (const id of scope.studentIds) query.append("student_id", String(id));
  return `/api/reports/pdf?${query}`;
}

/**
 * How a picker selection is delivered. One student, or students of one class printed as one
 * PDF, download at once; anything larger becomes a background job. A job names whole classes
 * when only whole classes are ticked, and the whole school when everyone is.
 */
export function planDelivery(
  roster: RosterClass[],
  selected: ReadonlySet<number>,
  format: ReportFormat,
): { direct: DirectScope } | { job: JobScope } {
  const touched = roster.filter((item) => item.students.some((s) => selected.has(s.id)));
  const whole = touched.filter((item) => item.students.every((s) => selected.has(s.id)));
  const studentIds = touched.flatMap((item) =>
    item.students.filter((s) => selected.has(s.id)).map((s) => s.id),
  );
  if (studentIds.length === 1) return { direct: { studentIds } };
  if (touched.length === 1 && format !== "per_student") {
    return { direct: whole.length === 1 ? { classId: touched[0].id } : { studentIds } };
  }
  if (whole.length === roster.length) return { job: { classIds: [], studentIds: [] } };
  if (whole.length === touched.length) {
    return { job: { classIds: whole.map((item) => item.id), studentIds: [] } };
  }
  return { job: { classIds: [], studentIds } };
}

function apiErrorCode(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = body.detail;
  if (!detail || typeof detail !== "object" || !("code" in detail)) return null;
  return typeof detail.code === "string" ? detail.code : null;
}

/** A failed API call as the same error the file helpers throw, with its `Retry-After`. */
function requestError(response: Response | undefined, body: unknown): FileRequestError {
  const retryAfter = Number(response?.headers.get("Retry-After"));
  return new FileRequestError(
    response?.status ?? 0,
    apiErrorCode(body),
    Number.isFinite(retryAfter) && retryAfter > 0 ? Math.ceil(retryAfter) : null,
  );
}

/** Queue a report set; failures throw `FileRequestError`. */
export async function startReportJob(
  semesterId: number,
  kind: ReportKind,
  locale: ReportLocale,
  format: ReportFormat,
  scope: JobScope,
): Promise<JobOut> {
  const { data, error, response } = await createReportJob({
    body: {
      semester_id: semesterId,
      kind,
      locale,
      format,
      class_ids: scope.classIds,
      student_ids: scope.studentIds,
    },
  });
  if (!data) throw requestError(response, error);
  return data;
}

/** Queue the whole-year XLSX export; failures throw `FileRequestError`. */
export async function startYearExport(yearId: number): Promise<JobOut> {
  const { data, error, response } = await createYearExportJob({ path: { year_id: yearId } });
  if (!data) throw requestError(response, error);
  return data;
}
