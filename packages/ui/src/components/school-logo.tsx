import { useState } from "react";

import { cn } from "#lib/utils";

/**
 * The school's logo.
 *
 * The real logo is NOT part of this open repository. `@flrc/branding` resolves
 * `src` to the runtime overlay (`/branding/logo.svg`, mounted by a deployment)
 * or to the bundled generic mark; see branding/README.md and ADR-054. Any raster
 * or vector format the browser can render works. The box has a fixed height and
 * grows in width (up to about 3:1), so a wide mark is not shrunk to fit a square.
 *
 * Until a real logo is served, the placeholder below renders, so the layout
 * never shows a broken image.
 */
export function SchoolLogo({
  src = "/school-logo.svg",
  schoolName,
  className,
}: {
  src?: string;
  schoolName: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const box = cn("h-9 max-w-28 shrink-0 rounded-lg", className);

  if (failed) return <PlaceholderMark className={cn(box, "aspect-square")} />;

  return (
    <img
      src={src}
      alt={schoolName}
      className={cn(box, "w-auto object-contain")}
      onError={() => setFailed(true)}
    />
  );
}

/** Neutral mark used until the school's own logo file is dropped in. */
function PlaceholderMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid place-items-center bg-primary text-primary-foreground",
        "text-[0.6875rem] font-bold tracking-tight",
        className,
      )}
    >
      FL
    </span>
  );
}
