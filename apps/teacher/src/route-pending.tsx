import { createElement, type ComponentType, type ReactElement } from "react";
import { useMatch, useRouterState } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { LOGO_URL, SCHOOL_SHORT_NAME } from "@flrc/branding";
import { AppShellSkeleton } from "@flrc/ui/components/app-shell-skeleton";
import { LoadingStatus } from "@flrc/ui/components/page-activity";
import type { FileRoutesById } from "./routeTree.gen";
import {
  CardPreviewSkeleton,
  ClassReportSkeleton,
  GridPageSkeleton,
  LoginSkeleton,
} from "./page-skeletons";

type PageRouteId = Exclude<keyof FileRoutesById, "__root__" | "/_auth" | "/login">;

/** Every signed-in page's loading shape; a new route fails the type check until it has one. */
const PAGE_SKELETONS: Record<PageRouteId, ComponentType> = {
  // The start page opens the teacher's first grade grid.
  "/_auth/": GridPageSkeleton,
  "/_auth/classes/$classId/$subject": GridPageSkeleton,
  "/_auth/class-report/": ClassReportSkeleton,
  "/_auth/class-report/$classId": ClassReportSkeleton,
  "/_auth/card-preview": CardPreviewSkeleton,
};

function pageSkeleton(routeId: string | undefined): ReactElement | undefined {
  return routeId !== undefined && routeId in PAGE_SKELETONS
    ? createElement(PAGE_SKELETONS[routeId as PageRouteId])
    : undefined;
}

/**
 * The router's pending view. A page whose code is still loading shows its own skeleton
 * inside the shell; before the session is known (the first load) the whole shell is drawn
 * as a skeleton around the target page's skeleton. Sign-in has no shell.
 */
export function RoutePending() {
  const { t } = useTranslation();
  const pendingRouteId = useMatch({
    strict: false,
    shouldThrow: false,
    select: (match) => match.routeId,
  });
  const leafRouteId = useRouterState({ select: (state) => state.matches.at(-1)?.routeId });

  const pendingPage = pageSkeleton(pendingRouteId);
  if (pendingPage) {
    return (
      <>
        <LoadingStatus label={t("loading")} />
        {pendingPage}
      </>
    );
  }

  if (leafRouteId === "/login") {
    return (
      <>
        <LoadingStatus label={t("loading")} />
        <LoginSkeleton />
      </>
    );
  }

  return (
    <AppShellSkeleton
      schoolName={SCHOOL_SHORT_NAME}
      schoolLogoUrl={LOGO_URL}
      workspaceLabel={t("shell.teacherWorkspace")}
      navGroups={[3, 4]}
      label={t("loading")}
    >
      {pageSkeleton(leafRouteId) ?? <GridPageSkeleton />}
    </AppShellSkeleton>
  );
}
