import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

export type PdfAction = "download" | "print" | "mine";

const PDF_LOCALES = ["tr", "en", "de", "fr"] as const;
/** How long a finished PDF's blob URL stays usable in the tab it opened. */
const PDF_URL_LIFETIME_MS = 300_000;

class PdfRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`Class report PDF failed (${status})`);
    this.status = status;
  }
}

async function fetchClassSheets(
  semesterId: number,
  classIds: number[],
  locale: string,
  signal: AbortSignal,
): Promise<Blob> {
  const query = new URLSearchParams({ semester_id: String(semesterId), locale });
  for (const classId of classIds) query.append("class_id", String(classId));
  const response = await fetch(`/api/reports/class-sheets?${query}`, {
    headers: { Accept: "application/pdf" },
    signal,
  });
  if (!response.ok) throw new PdfRequestError(response.status);
  return response.blob();
}

/**
 * Download or print class sheets. One request runs at a time: the server counts
 * PDFs against a small per-teacher budget, so a second click must not start another.
 */
export function useClassSheetPdf() {
  const { t, i18n } = useTranslation();
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
    deliver: (url: string) => void,
    abandon?: () => void,
  ) {
    if (inFlight.current || classIds.length === 0) {
      abandon?.();
      return;
    }
    const controller = new AbortController();
    inFlight.current = controller;
    setPending(action);
    try {
      const blob = await fetchClassSheets(semesterId, classIds, locale, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      window.setTimeout(() => URL.revokeObjectURL(url), PDF_URL_LIFETIME_MS);
      deliver(url);
    } catch (error) {
      abandon?.();
      if (controller.signal.aborted) return;
      toast.error(
        error instanceof PdfRequestError && error.status === 429
          ? t("classReport.rateLimited")
          : t("reports.pdfFailed"),
      );
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setPending(null);
      }
    }
  }

  /** Save the PDF under a readable file name. */
  function download(action: PdfAction, semesterId: number, classIds: number[], fileName: string) {
    void run(action, semesterId, classIds, (url) => {
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = fileName;
      anchor.click();
    });
  }

  /**
   * Open the PDF in a new tab to print it there. The tab is opened during the click,
   * before the PDF exists, so pop-up blockers allow it; it shows a short notice until
   * the file arrives.
   */
  function print(semesterId: number, classIds: number[]) {
    const tab = window.open("", "_blank");
    if (tab) {
      tab.document.title = t("classReport.preparing");
      tab.document.body.textContent = t("classReport.preparing");
    }
    void run(
      "print",
      semesterId,
      classIds,
      (url) => {
        if (tab && !tab.closed) {
          tab.location.replace(url);
          return;
        }
        toast.success(t("reports.pdfReady"), {
          action: {
            label: t("reports.openReadyPdf"),
            onClick: () => window.open(url, "_blank"),
          },
          duration: PDF_URL_LIFETIME_MS,
        });
      },
      () => tab?.close(),
    );
  }

  return { pending, download, print };
}
