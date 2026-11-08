/**
 * The page's one polite "Loading…" announcement while its first data loads. Sighted
 * users see the page's skeleton instead, so the status itself stays visually hidden.
 * It is always mounted: a live region that exists before its text changes is announced
 * reliably.
 */
function PageActivity({ active, label }: { active: boolean; label: string }) {
  return (
    <p role="status" className="sr-only">
      {active ? label : null}
    </p>
  );
}

/** A loading announcement for a skeleton shown where no `PageActivity` is listening. */
function LoadingStatus({ label }: { label: string }) {
  return (
    <p role="status" className="sr-only">
      {label}
    </p>
  );
}

export { LoadingStatus, PageActivity };
