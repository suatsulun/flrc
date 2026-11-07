/**
 * Browser-side delivery of server-built files (PDF report cards, class sheets, ZIP sets), shared
 * by both panels.
 *
 * - File names come from the server's `Content-Disposition`, so a file is named the same way
 *   wherever it was requested.
 * - Pop-up blockers only allow a tab opened during the click. `openPendingTab` opens it then, and
 *   `showInTab` fills it once the file exists; when the tab is gone the caller saves the file.
 * - Object URLs are released on a timer after they are handed over; no UI keeps a link to them.
 */

/** A failed file request, with the API's machine code and the server's `Retry-After`. */
export class FileRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly retryAfterSeconds: number | null;

  constructor(status: number, code: string | null, retryAfterSeconds: number | null) {
    super(`File request failed (${status}${code ? `: ${code}` : ""})`);
    this.name = "FileRequestError";
    this.status = status;
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  get rateLimited(): boolean {
    return this.status === 429;
  }
}

export type FetchedFile = { blob: Blob; filename: string | null };

/** Saved files only need their URL until the download starts. */
const DOWNLOAD_URL_LIFETIME_MS = 60_000;
/** A viewer tab may re-read its URL to print or save, so it keeps it longer. */
const TAB_URL_LIFETIME_MS = 300_000;

/** The file name from a `Content-Disposition` header, preferring RFC 5987 `filename*`. */
export function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const extended = /filename\*\s*=\s*[^']*'[^']*'([^;]+)/i.exec(header);
  if (extended?.[1]) {
    try {
      return decodeURIComponent(extended[1].trim().replace(/^"|"$/g, ""));
    } catch {
      // A malformed encoding falls back to the plain parameter.
    }
  }
  const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/i.exec(header);
  const value = (plain?.[1] ?? plain?.[2])?.trim();
  return value || null;
}

function errorCode(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = body.detail;
  if (!detail || typeof detail !== "object" || !("code" in detail)) return null;
  return typeof detail.code === "string" ? detail.code : null;
}

async function requestError(response: Response): Promise<FileRequestError> {
  let code: string | null = null;
  try {
    code = errorCode(await response.json());
  } catch {
    // Error bodies that are not JSON carry no code.
  }
  const retryAfter = Number(response.headers.get("Retry-After"));
  return new FileRequestError(
    response.status,
    code,
    Number.isFinite(retryAfter) && retryAfter > 0 ? Math.ceil(retryAfter) : null,
  );
}

/** Fetch a file from the API; non-2xx responses throw `FileRequestError`. */
export async function fetchFile(input: string, init: RequestInit = {}): Promise<FetchedFile> {
  const response = await fetch(input, { credentials: "same-origin", ...init });
  if (!response.ok) throw await requestError(response);
  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition")),
  };
}

/** Whether an error only reports that the caller aborted its own request. */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Save a fetched file under its server-given name. */
export function saveFile(file: FetchedFile, fallbackName: string): void {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename ?? fallbackName;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_LIFETIME_MS);
}

/** Open a placeholder tab during the click so a later `showInTab` is not blocked. */
export function openPendingTab(message: string): Window | null {
  const tab = window.open("", "_blank");
  if (tab) {
    tab.document.title = message;
    tab.document.body.textContent = message;
  }
  return tab;
}

/**
 * Show a fetched file in a tab from `openPendingTab`. Returns false when the tab was blocked or
 * closed, so the caller can save the file instead.
 */
export function showInTab(tab: Window | null, file: FetchedFile): boolean {
  if (!tab || tab.closed) return false;
  const url = URL.createObjectURL(file.blob);
  tab.location.replace(url);
  window.setTimeout(() => URL.revokeObjectURL(url), TAB_URL_LIFETIME_MS);
  return true;
}
