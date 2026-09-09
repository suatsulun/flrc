import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import * as Sentry from "@sentry/react";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { client } from "@flrc/api-client";
import { i18n, initI18n } from "@flrc/i18n";
import { Toaster } from "@flrc/ui/components/sonner";
import { FullScreenLoading } from "@flrc/ui/components/page-activity";
import { toast } from "sonner";
import { routeTree } from "./routeTree.gen";
import "./index.css";

client.setConfig({ baseUrl: "" });
initI18n();
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    sendDefaultPii: false,
    tracesSampleRate: 0,
  });
}

const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onError: () => toast.error(i18n.t("feedback.actionFailed")),
  }),
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPendingMs: 150,
  defaultPendingMinMs: 300,
  defaultPendingComponent: () => <FullScreenLoading label={i18n.t("loading")} />,
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
      <Toaster richColors position="bottom-center" />
    </QueryClientProvider>
  </StrictMode>,
);
