/** `45.5` → "45.5%" / "%45,5", in the reader's language. */
export function formatPercent(value: number, language: string): string {
  return new Intl.NumberFormat(language, { style: "percent", maximumFractionDigits: 1 }).format(
    value / 100,
  );
}

/** The API writes job times as UTC without an offset; read them as UTC, not local time. */
export function parseUtc(value: string): Date {
  return new Date(/(?:[zZ]|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
}
