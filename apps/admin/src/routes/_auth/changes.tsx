import { useInfiniteQuery } from "@tanstack/react-query";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { listAdminActions, listAdminActionsInfiniteQueryKey } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { SkeletonList, SkeletonTableRows } from "@flrc/ui/components/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableScroll,
  TableText,
} from "@flrc/ui/components/table";
import { AdminPage } from "../../admin/AdminPage";
import { ChangesSkeleton } from "../../admin/page-skeletons";
import { ChangeStatusBadge, UndoChangeButton } from "../../changes/ChangeControls";
import { changeSummary, formatChangeTime } from "../../changes/summary";

const PAGE_SIZE = 50;

export const Route = createFileRoute("/_auth/changes")({
  // Undo is an administrator's tool (ADR-075); coordinators land on the dashboard.
  beforeLoad: ({ context }) => {
    if (!context.user.is_admin) throw redirect({ to: "/", replace: true });
  },
  component: ChangesPage,
});

/** Every recorded admin change of the last 7 days, newest first, each with its own Undo. */
function ChangesPage() {
  const { t, i18n } = useTranslation();
  const changes = useInfiniteQuery({
    queryKey: listAdminActionsInfiniteQueryKey({ query: { limit: PAGE_SIZE } }),
    queryFn: async ({ pageParam, signal }) => {
      const { data } = await listAdminActions({
        query: { limit: PAGE_SIZE, cursor: pageParam },
        signal,
        throwOnError: true,
      });
      return data;
    },
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  if (changes.isPending) return <ChangesSkeleton />;
  // A failed "Load more" or background refresh keeps the rows already on screen.
  if (!changes.data) return <EmptyState title={t("errors.load")} />;

  const items = changes.data.pages.flatMap((page) => page.items);
  const now = changes.dataUpdatedAt;

  return (
    <AdminPage title={t("changes.title")} description={t("changes.description")}>
      <Card>
        {items.length === 0 ? (
          <CardBody>
            <p className="px-5 py-6 text-sm text-muted-foreground">{t("changes.empty")}</p>
          </CardBody>
        ) : (
          <>
            <CardBody className="hidden md:block">
              <TableScroll aria-label={t("changes.tableLabel")}>
                <Table className="min-w-[56rem]">
                  <TableCaption>{t("changes.tableLabel")}</TableCaption>
                  <TableHead>
                    <tr>
                      <TableHeader className="min-w-80">{t("changes.change")}</TableHeader>
                      <TableHeader className="min-w-36">{t("changes.who")}</TableHeader>
                      <TableHeader className="w-40">{t("changes.when")}</TableHeader>
                      <TableHeader className="min-w-44">{t("changes.status")}</TableHeader>
                      <TableHeader className="w-32" align="right">
                        {t("changes.actions")}
                      </TableHeader>
                    </tr>
                  </TableHead>
                  <TableBody>
                    {items.map((action) => (
                      <TableRow key={action.id} data-testid="change-row">
                        <TableCell className="font-medium">{changeSummary(t, action)}</TableCell>
                        <TableCell>
                          <TableText className="max-w-40">
                            {action.actor ?? t("changes.unknownActor")}
                          </TableText>
                        </TableCell>
                        <TableCell className="tabular text-xs text-muted-foreground">
                          {formatChangeTime(action.created_at, i18n.language)}
                        </TableCell>
                        <TableCell>
                          <ChangeStatusBadge action={action} now={now} />
                        </TableCell>
                        <TableCell align="right">
                          {action.status === "available" ? (
                            <UndoChangeButton action={action} />
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                    {changes.isFetchingNextPage ? <SkeletonTableRows columns={5} /> : null}
                  </TableBody>
                </Table>
              </TableScroll>
            </CardBody>
            <ul className="divide-y divide-border md:hidden" aria-label={t("changes.tableLabel")}>
              {items.map((action) => (
                <li key={action.id} data-testid="change-card" className="space-y-2 px-4 py-3">
                  <p className="text-sm font-medium">{changeSummary(t, action)}</p>
                  <p className="text-xs text-muted-foreground">
                    {action.actor ?? t("changes.unknownActor")} ·{" "}
                    {formatChangeTime(action.created_at, i18n.language)}
                  </p>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <ChangeStatusBadge action={action} now={now} />
                    {action.status === "available" ? <UndoChangeButton action={action} /> : null}
                  </div>
                </li>
              ))}
            </ul>
            {changes.isFetchingNextPage ? (
              <SkeletonList rows={3} action className="border-t border-border md:hidden" />
            ) : null}
          </>
        )}
      </Card>

      {changes.isFetchNextPageError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-center gap-3 text-sm text-destructive"
        >
          <p>{t("changes.loadMoreFailed")}</p>
          <Button
            variant="outline"
            pending={changes.isFetchingNextPage}
            pendingLabel={t("loading")}
            onClick={() => void changes.fetchNextPage()}
          >
            {t("changes.retry")}
          </Button>
        </div>
      ) : changes.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            pending={changes.isFetchingNextPage}
            pendingLabel={t("loading")}
            onClick={() => void changes.fetchNextPage()}
          >
            {t("changes.loadMore")}
          </Button>
        </div>
      ) : null}
    </AdminPage>
  );
}
