import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  fetchFile,
  isAbortError,
  openPendingTab,
  saveFile,
  showInTab,
} from "@flrc/ui/lib/file-delivery";
import { reportRequestMessage } from "./report-errors";

export type DirectAction = "view" | "download";
export type DirectPending = { key: string; action: DirectAction };

/** The page's single direct-download channel. */
export type DirectDownload = {
  /** The request in flight, or null. */
  pending: DirectPending | null;
  /** Fetch and deliver one PDF; resolves to whether it was delivered. */
  run: (key: string, action: DirectAction, url: string) => Promise<boolean>;
  /** Abort the request in flight. */
  stop: () => void;
};

/**
 * One class's or a few students' report PDF, fetched at once. One request runs at a time; the
 * page keeps a leave guard up while it does, and leaving aborts it.
 */
export function useDirectDownload(): DirectDownload {
  const { t } = useTranslation();
  const [pending, setPending] = useState<DirectPending | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      inFlight.current?.abort();
      inFlight.current = null;
    },
    [],
  );

  /**
   * View opens its tab during the click so pop-up blockers allow it; a blocked or closed tab
   * falls back to saving the file. Resolves to whether the file was delivered.
   */
  async function run(key: string, action: DirectAction, url: string): Promise<boolean> {
    if (inFlight.current) return false;
    const tab = action === "view" ? openPendingTab(t("reports.preparingTab")) : null;
    const controller = new AbortController();
    inFlight.current = controller;
    setPending({ key, action });
    try {
      const file = await fetchFile(url, {
        headers: { Accept: "application/pdf" },
        signal: controller.signal,
      });
      if (action === "download" || !showInTab(tab, file)) saveFile(file, "report.pdf");
      return true;
    } catch (error) {
      tab?.close();
      if (!isAbortError(error) && !controller.signal.aborted) {
        toast.error(reportRequestMessage(t, error));
      }
      return false;
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setPending(null);
      }
    }
  }

  function stop() {
    inFlight.current?.abort();
    inFlight.current = null;
    setPending(null);
  }

  return { pending, run, stop };
}
