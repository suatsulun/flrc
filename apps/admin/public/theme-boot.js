/**
 * Stamps the resolved theme on <html> before the first paint, so an overridden
 * preference never flashes the wrong palette.
 *
 * This lives as a static file rather than an inline <script> because the app's
 * Content-Security-Policy is `script-src 'self'` (see public/_headers) and does
 * not permit inline script. Keep it in sync with applyTheme() in
 * packages/ui/src/lib/theme.ts — the storage key is "flrc-theme".
 */
(function () {
  try {
    var stored = localStorage.getItem("flrc-theme");
    var dark =
      stored === "dark" ||
      (stored !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
    var root = document.documentElement;
    root.classList.add(dark ? "dark" : "light");
    root.style.colorScheme = dark ? "dark" : "light";
  } catch (error) {
    /* Private browsing can block storage; the light default still applies. */
  }
})();
