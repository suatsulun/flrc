import { createFileRoute, redirect } from "@tanstack/react-router";

/** The coordinator page became the landing dashboard (ADR-079); old links and bookmarks land there. */
export const Route = createFileRoute("/_auth/coordinator")({
  beforeLoad: () => {
    throw redirect({ to: "/", replace: true });
  },
});
