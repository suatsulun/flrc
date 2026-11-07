import { i18n } from "@flrc/i18n";

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

/**
 * The localized message for a failed admin action: a specific sentence per API error code,
 * the blocking reason for a refused undo, and the generic failure text otherwise.
 */
export function errorMessage(error: unknown): string {
  const { code, reason, params } = apiError(error);
  if (code === "undo_blocked" && reason && i18n.exists(`changes.blocked.${reason}`)) {
    return i18n.t(`changes.blocked.${reason}`, params);
  }
  if (code && i18n.exists(`errors.codes.${code}`)) return i18n.t(`errors.codes.${code}`, params);
  return i18n.t("feedback.actionFailed");
}
