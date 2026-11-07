import { createElement, type ComponentType, type ReactElement } from "react";
import { useMatch, useRouterState } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { LOGO_URL, SCHOOL_SHORT_NAME } from "@flrc/branding";
import { AppShellSkeleton } from "@flrc/ui/components/app-shell-skeleton";
import { LoadingStatus } from "@flrc/ui/components/page-activity";
import type { FileRoutesById } from "../routeTree.gen";
import {
  ArchiveSkeleton,
  AssignmentsSkeleton,
  AuditSkeleton,
  ChangesSkeleton,
  ClassesSkeleton,
  ColumnsSkeleton,
  DashboardSkeleton,
  ImportSkeleton,
  LifecycleSkeleton,
  ReportsSkeleton,
  StudentHistorySkeleton,
  StudentsSkeleton,
  UsersSkeleton,
} from "./page-skeletons";

type PageRouteId = Exclude<keyof FileRoutesById, "__root__" | "/_auth">;

/** Every page's loading shape; a new route fails the type check until it has one. */
const PAGE_SKELETONS: Record<PageRouteId, ComponentType> = {
  "/_auth/": DashboardSkeleton,
  "/_auth/coordinator": DashboardSkeleton,
  "/_auth/classes": ClassesSkeleton,
  "/_auth/columns": ColumnsSkeleton,
  "/_auth/students/": StudentsSkeleton,
  "/_auth/students/$studentId/history": StudentHistorySkeleton,
  "/_auth/users": UsersSkeleton,
  "/_auth/assignments": AssignmentsSkeleton,
  "/_auth/lifecycle": LifecycleSkeleton,
  "/_auth/import": ImportSkeleton,
  "/_auth/audit": AuditSkeleton,
  "/_auth/changes": ChangesSkeleton,
  "/_auth/reports": ReportsSkeleton,
  "/_auth/archive": ArchiveSkeleton,
};

function pageSkeleton(routeId: string | undefined): ReactElement | undefined {
  return routeId !== undefined && routeId in PAGE_SKELETONS
    ? createElement(PAGE_SKELETONS[routeId as PageRouteId])
    : undefined;
}

/**
 * The router's pending view. A page whose code is still loading shows its own skeleton
 * inside the shell; before the session is known (the first load) the whole shell is drawn
 * as a skeleton around the target page's skeleton.
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

  return (
    <AppShellSkeleton
      schoolName={SCHOOL_SHORT_NAME}
      schoolLogoUrl={LOGO_URL}
      workspaceLabel={t("shell.adminWorkspace")}
      navGroups={[2, 2, 3, 4]}
      label={t("loading")}
    >
      {pageSkeleton(leafRouteId) ?? <DashboardSkeleton />}
    </AppShellSkeleton>
  );
}
