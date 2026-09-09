import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { DownloadIcon, FlagIcon, KeyRoundIcon } from "lucide-react";
import { toast } from "sonner";
import { listAudit, listClassesOptions } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
  TableScroll,
  TableText,
} from "@flrc/ui/components/table";
import { AdminPage } from "../../admin/AdminPage";

export const Route = createFileRoute("/_auth/audit")({ component: AuditPage });

function AuditPage() {
  const { t, i18n } = useTranslation();
  const [classId, setClassId] = useState<number>();
  const [exportPending, setExportPending] = useState(false);
  const {
    data: classes = [],
    isPending: classesPending,
    isError: classesError,
  } = useQuery(listClassesOptions());
  const audit = useInfiniteQuery({
    queryKey: ["audit", classId],
    queryFn: async ({ pageParam }) => {
      const result = await listAudit({ query: { class_id: classId, cursor: pageParam } });
      if (result.error) throw result.error;
      if (!result.data) throw new Error("audit_unavailable");
      return result.data;
    },
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = audit.data?.pages.flatMap((page) => page.items) ?? [];
  const exportUrl = `/api/audit/export.csv${classId ? `?class_id=${classId}` : ""}`;

  async function exportAudit() {
    setExportPending(true);
    toast.loading(t("audit.exporting"), { id: "audit-csv" });
    try {
      const response = await fetch(exportUrl);
      if (!response.ok) throw new Error(`Audit export failed (${response.status})`);
      const href = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = "audit.csv";
      anchor.click();
      URL.revokeObjectURL(href);
      toast.success(t("audit.exportReady"), { id: "audit-csv" });
    } catch {
      toast.error(t("feedback.actionFailed"), { id: "audit-csv" });
    } finally {
      setExportPending(false);
    }
  }

  if (classesPending || audit.isPending) return <PageSkeleton />;
  if (classesError || audit.isError) return <EmptyState title={t("errors.load")} />;

  return (
    <AdminPage
      title={t("audit.title")}
      description={t("audit.description")}
      actions={
        <>
          <NativeSelect
            className="w-44"
            aria-label={t("audit.allClasses")}
            value={classId ?? ""}
            onChange={(event) =>
              setClassId(event.target.value ? Number(event.target.value) : undefined)
            }
          >
            <option value="">{t("audit.allClasses")}</option>
            {classes.map((schoolClass) => (
              <option key={schoolClass.id} value={schoolClass.id}>
                {schoolClass.name}
              </option>
            ))}
          </NativeSelect>
          <Button
            variant="outline"
            pending={exportPending}
            pendingLabel={t("audit.exporting")}
            onClick={() => void exportAudit()}
          >
            <DownloadIcon />
            {t("audit.exportCsv")}
          </Button>
        </>
      }
    >
      <Card>
        <CardBody>
          <TableScroll aria-label={t("audit.tableLabel")}>
            <Table className="min-w-[64rem]">
              <TableCaption>{t("audit.tableLabel")}</TableCaption>
              <TableHead>
                <tr>
                  <TableHeader className="sticky left-0 z-30 w-44 border-r bg-muted/95">
                    {t("audit.when")}
                  </TableHeader>
                  <TableHeader className="min-w-40">{t("audit.actor")}</TableHeader>
                  <TableHeader className="min-w-48">{t("audit.student")}</TableHeader>
                  <TableHeader className="min-w-40">{t("audit.column")}</TableHeader>
                  <TableHeader className="min-w-40">{t("audit.change")}</TableHeader>
                  <TableHeader className="w-24" align="right">
                    {t("audit.flags")}
                  </TableHeader>
                </tr>
              </TableHead>
              <TableBody>
                {items.length === 0 ? (
                  <TableEmpty colSpan={6}>{t("audit.empty")}</TableEmpty>
                ) : (
                  items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="tabular sticky left-0 z-10 border-r bg-card text-xs text-muted-foreground group-even:bg-muted group-hover:bg-accent">
                        {new Date(item.created_at).toLocaleString(i18n.language)}
                      </TableCell>
                      <TableCell>
                        <TableText className="max-w-40">{item.actor}</TableText>
                      </TableCell>
                      <TableCell className="font-medium">
                        <TableText className="max-w-48">{item.student}</TableText>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        <TableText className="max-w-40">{item.column_label}</TableText>
                      </TableCell>
                      <TableCell>
                        <span className="tabular flex items-center gap-1.5 text-xs">
                          <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">
                            {item.old_existed ? (item.old_value ?? "—") : "∅"}
                          </span>
                          <span className="text-muted-foreground">→</span>
                          <span className="rounded bg-accent px-1.5 py-0.5 font-medium text-accent-foreground">
                            {item.new_value ?? "—"}
                          </span>
                        </span>
                      </TableCell>
                      <TableCell align="right">
                        <span className="flex justify-end gap-1">
                          {item.forced ? (
                            <Badge
                              tone="warning"
                              title={t("audit.forced")}
                              aria-label={t("audit.forced")}
                            >
                              <FlagIcon />
                            </Badge>
                          ) : null}
                          {item.via_grant ? (
                            <Badge
                              tone="info"
                              title={t("audit.viaGrant")}
                              aria-label={t("audit.viaGrant")}
                            >
                              <KeyRoundIcon />
                            </Badge>
                          ) : null}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableScroll>
        </CardBody>
      </Card>

      {audit.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            pending={audit.isFetchingNextPage}
            pendingLabel={t("loading")}
            onClick={() => audit.fetchNextPage()}
          >
            {t("audit.loadMore")}
          </Button>
        </div>
      ) : null}
    </AdminPage>
  );
}
