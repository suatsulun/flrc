import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import * as Sentry from "@sentry/react";
import { sentryPrivacyOptions } from "@flrc/ui/lib/telemetry";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { client } from "@flrc/api-client";
import { initI18n } from "@flrc/i18n";
import { toast } from "sonner";
import { routeTree } from "./routeTree.gen";
import { errorMessage } from "./admin/feedback";
import { RoutePending } from "./admin/route-pending";
import "./index.css";

client.setConfig({ baseUrl: "" });
initI18n();
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    ...sentryPrivacyOptions(),
  });
}

const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    // Every failed admin write explains itself; a mutation that shows its own error inline
    // opts out with `meta: { silentError: true }`.
    onError: (error, _variables, _context, mutation) => {
      if (mutation.meta?.silentError === true) return;
      toast.error(errorMessage(error));
    },
  }),
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

const router = createRouter({
  routeTree,
  context: { queryClient },
  basepath: "/admin",
  defaultPendingMs: 150,
  defaultPendingMinMs: 300,
  defaultPendingComponent: RoutePending,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
