/**
 * `45.5` → "45.5%" / "%45,5", in the reader's language. Truncated, never rounded up: 99.99%
 * must not read as 100% while a single grade is still missing.
 */
export function formatPercent(value: number, language: string): string {
  const truncated = Math.floor(value * 10) / 10;
  return new Intl.NumberFormat(language, { style: "percent", maximumFractionDigits: 1 }).format(
    truncated / 100,
  );
}

/** The API writes job times as UTC without an offset; read them as UTC, not local time. */
export function parseUtc(value: string): Date {
  return new Date(/(?:[zZ]|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
}
