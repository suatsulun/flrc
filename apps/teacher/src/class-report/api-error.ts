/** The machine code of an API error body, such as `{"detail": {"code": "…"}}`. */
export function errorCode(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const { detail } = error;
  return typeof detail === "object" && detail !== null && "code" in detail
    ? String(detail.code)
    : undefined;
}
