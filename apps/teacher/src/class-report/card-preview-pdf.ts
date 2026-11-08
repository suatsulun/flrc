import type { PreviewClassOut } from "@flrc/api-client";
import { fetchFile, isAbortError } from "@flrc/ui/lib/file-delivery";
import { useEffect, useState } from "react";

export type CardKind = PreviewClassOut["kind"];

export type CardPreviewRequest = { semesterId: number; studentId: number; kind: CardKind };

/**
 * Paging waits this long for the selection to settle, so holding an arrow key renders the card
 * the teacher stops on instead of spending the per-minute PDF budget on every card passed.
 */
const SETTLE_MS = 250;

type Loaded = { key: string; url: string | null; error: unknown };

export type CardPreviewState =
  | { status: "idle" | "loading"; url: string | null }
  | { status: "ready"; url: string }
  | { status: "error"; url: string | null; error: unknown };

/**
 * One student's watermarked card as a `blob:` URL for an on-screen viewer. Each URL is revoked
 * as soon as a newer card replaces it or the viewer unmounts. While a new card loads the previous
 * one stays available so the viewer can keep it on screen behind a loading notice.
 */
export function useCardPreviewPdf(request: CardPreviewRequest | null) {
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const semesterId = request?.semesterId;
  const studentId = request?.studentId;
  const kind = request?.kind;
  const key =
    semesterId === undefined || studentId === undefined || kind === undefined
      ? null
      : `${semesterId}:${kind}:${studentId}:${attempt}`;

  useEffect(() => {
    if (key === null || semesterId === undefined || studentId === undefined || !kind) return;
    const controller = new AbortController();
    const query = new URLSearchParams({
      semester_id: String(semesterId),
      student_id: String(studentId),
      kind,
    });
    const timer = window.setTimeout(() => {
      fetchFile(`/api/reports/preview?${query}`, {
        headers: { Accept: "application/pdf" },
        signal: controller.signal,
      }).then(
        (file) => {
          if (controller.signal.aborted) return;
          setLoaded({ key, url: URL.createObjectURL(file.blob), error: null });
        },
        (error: unknown) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          setLoaded({ key, url: null, error });
        },
      );
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [key, semesterId, studentId, kind]);

  // The previous card's URL is released once the next one (or nothing) replaces it.
  const url = loaded?.url ?? null;
  useEffect(() => {
    if (!url) return;
    return () => URL.revokeObjectURL(url);
  }, [url]);

  const retry = () => setAttempt((count) => count + 1);

  let state: CardPreviewState;
  if (key === null) state = { status: "idle", url: null };
  else if (loaded?.key !== key) state = { status: "loading", url };
  else if (loaded.url) state = { status: "ready", url: loaded.url };
  else state = { status: "error", url: null, error: loaded.error };
  return { ...state, retry };
}
