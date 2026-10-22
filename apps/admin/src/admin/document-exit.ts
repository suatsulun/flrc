import type { AnyRouter } from "@tanstack/react-router";

/**
 * Asks the page's leave guards before a full-document exit (sign-out, the teacher panel).
 *
 * The router checks blockers for document navigations with the current location as the
 * destination, which is indistinguishable from following a link to the page already open, so
 * exits run the blockers themselves with their real destination. Resolves true when the exit may
 * proceed; navigate with `ignoreBlocker` afterwards so the page is not asked twice.
 */
export async function allowDocumentExit(router: AnyRouter, href: string): Promise<boolean> {
  const here = router.history.location;
  const url = new URL(href, window.location.href);
  const destination = {
    ...here,
    href: `${url.pathname}${url.search}${url.hash}`,
    pathname: url.pathname,
    search: url.search,
    hash: url.hash,
  };
  for (const { blockerFn } of router.history._getBlockers()) {
    if (await blockerFn({ currentLocation: here, nextLocation: destination, action: "PUSH" })) {
      return false;
    }
  }
  return true;
}
