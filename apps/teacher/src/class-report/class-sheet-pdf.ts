import {
  FileRequestError,
  fetchFile,
  isAbortError,
  openPendingTab,
  saveFile,
  showInTab,
  type FetchedFile,
} from "@flrc/ui/lib/file-delivery";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

export type PdfAction = "download" | "print" | "mine";

const PDF_LOCALES = ["tr", "en", "de", "fr"] as const;

/** Windows-safe file name part: `/` in class names becomes `-`, reserved characters go. */
function filePart(value: string) {
  return value
    .replace(/\//g, "-")
    .replace(/[\\:*?"<>|]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The server names class-sheet files; this is only the fallback when its header is missing:
 * `8-A Sınıf Raporu 2026-2027 1. Dönem.pdf`, or `Sınıf Raporları …` for several classes.
 */
export function classSheetFileName(
  className: string | null,
  yearLabel: string,
  semesterNumber: number,
) {
  const scope = className ? `${filePart(className)} Sınıf Raporu` : "Sınıf Raporları";
  return `${scope} ${filePart(yearLabel)} ${semesterNumber}. Dönem.pdf`;
}

/** The message for a failed PDF request, with the wait from `Retry-After` when rate-limited. */
export function usePdfErrorMessage() {
  const { t } = useTranslation();
  return (error: unknown) => {
    if (error instanceof FileRequestError && error.rateLimited) {
      return error.retryAfterSeconds
        ? t("classReport.rateLimitedWait", { seconds: error.retryAfterSeconds })
        : t("classReport.rateLimited");
    }
    return t("reports.pdfFailed");
  };
}

/**
 * Download or print class sheets. One request runs at a time: the server counts PDFs against a
 * per-teacher budget, so a second click must not start another.
 */
export function useClassSheetPdf() {
  const { t, i18n } = useTranslation();
  const errorMessage = usePdfErrorMessage();
  const [pending, setPending] = useState<PdfAction | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  const locale = PDF_LOCALES.find((code) => i18n.language.startsWith(code)) ?? "tr";

  useEffect(
    () => () => {
      inFlight.current?.abort();
      inFlight.current = null;
    },
    [],
  );

  async function run(
    action: PdfAction,
    semesterId: number,
    classIds: number[],
    deliver: (file: FetchedFile) => void,
    abandon?: () => void,
  ) {
    if (inFlight.current || classIds.length === 0) {
      abandon?.();
      return;
    }
    const controller = new AbortController();
    inFlight.current = controller;
    setPending(action);
    const query = new URLSearchParams({ semester_id: String(semesterId), locale });
    for (const classId of classIds) query.append("class_id", String(classId));
    try {
      const file = await fetchFile(`/api/reports/class-sheets?${query}`, {
        headers: { Accept: "application/pdf" },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      deliver(file);
    } catch (error) {
      abandon?.();
      if (controller.signal.aborted || isAbortError(error)) return;
      toast.error(errorMessage(error));
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setPending(null);
      }
    }
  }

  /** Save the PDF under the server's file name. */
  function download(action: PdfAction, semesterId: number, classIds: number[], fallback: string) {
    void run(action, semesterId, classIds, (file) => saveFile(file, fallback));
  }

  /**
   * Open the PDF in a new tab to print it there. The tab opens during the click, before the PDF
   * exists, so pop-up blockers allow it; if it was blocked or closed, the file is saved instead.
   */
  function print(semesterId: number, classIds: number[], fallback: string) {
    const tab = openPendingTab(t("classReport.preparing"));
    void run(
      "print",
      semesterId,
      classIds,
      (file) => {
        if (!showInTab(tab, file)) saveFile(file, fallback);
      },
      () => tab?.close(),
    );
  }

  /** Stop the PDF in flight, for a teacher who chose to leave the page. */
  function cancel() {
    inFlight.current?.abort();
  }

  return { pending, download, print, cancel };
}
