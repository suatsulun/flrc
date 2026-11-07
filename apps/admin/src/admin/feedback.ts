import { gradeLabel, i18n } from "@flrc/i18n";

/** The machine-readable parts of a failed API call (`HTTPException` detail objects). */
export type ApiError = {
  code: string | null;
  reason: string | null;
  params: Record<string, string | number>;
};

const NO_DETAIL: ApiError = { code: null, reason: null, params: {} };

function readParams(value: unknown): Record<string, string | number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const params: Record<string, string | number> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === "string" || typeof entry === "number") params[key] = entry;
  }
  return params;
}

/**
 * Read a generated-client error. Mutations run with `throwOnError`, which throws the parsed
 * response body: `{ detail: { code, reason?, params? } }` for API errors and
 * `{ detail: [...] }` for request validation failures.
 */
export function apiError(error: unknown): ApiError {
  if (!error || typeof error !== "object" || !("detail" in error)) return NO_DETAIL;
  const detail = error.detail;
  if (Array.isArray(detail)) return { ...NO_DETAIL, code: "invalid_request" };
  if (!detail || typeof detail !== "object") return NO_DETAIL;
  const code = "code" in detail && typeof detail.code === "string" ? detail.code : null;
  const reason = "reason" in detail && typeof detail.reason === "string" ? detail.reason : null;
  const params = "params" in detail ? readParams(detail.params) : {};
  return { code, reason, params };
}

/** API params carry codes (`main`, `german`, `5`); a sentence needs their localized names. */
function localizeParams(params: Record<string, string | number>) {
  const values: Record<string, string | number> = { ...params };
  if (typeof params.role === "string") values.role = i18n.t(`roles.${params.role}`);
  if (typeof params.subject === "string") values.subject = i18n.t(`subjects.${params.subject}`);
  if (typeof params.grade_level === "number") {
    values.grade_level = gradeLabel(i18n.t, params.grade_level);
  }
  return values;
}

/**
 * Which record an undo refusal names. The same reason reads differently for a student, a
 * field, an account, a class or one teaching slot of a class, so each gets its own sentence
 * (i18next `context`), with the plain sentence for a refusal that names nothing.
 */
function refusalSubject(params: Record<string, string | number>): string | undefined {
  if ("student" in params) return "student";
  if ("field" in params) return "field";
  if ("user" in params) return "user";
  if ("class" in params) return "role" in params ? "slot" : "class";
  if ("role" in params) return "role";
  if ("grade_level" in params) return "scope";
  if ("count" in params) return "count";
  return undefined;
}

/**
 * The localized message for a failed admin action: a specific sentence per API error code,
 * the blocking reason for a refused undo, and the generic failure text otherwise.
 */
export function errorMessage(error: unknown): string {
  const { code, reason, params } = apiError(error);
  const values = localizeParams(params);
  if (code === "undo_blocked" && reason) {
    if (i18n.exists(`changes.blocked.${reason}`)) {
      return i18n.t(`changes.blocked.${reason}`, { ...values, context: refusalSubject(params) });
    }
    // The original endpoint's own rule (archived year, last administrator, ...).
    if (i18n.exists(`errors.codes.${reason}`)) return i18n.t(`errors.codes.${reason}`, values);
  }
  if (code && i18n.exists(`errors.codes.${code}`)) return i18n.t(`errors.codes.${code}`, values);
  return i18n.t("feedback.actionFailed");
}
