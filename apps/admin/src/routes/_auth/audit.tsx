import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { DownloadIcon, FlagIcon, KeyRoundIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import {
  listAudit,
  listClassesOptions,
  listUsersOptions,
  type AuditItemOut,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardContent } from "@flrc/ui/components/card";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Field } from "@flrc/ui/components/field";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { PhoneCardHeader, PhoneCardItem, PhoneCardList } from "@flrc/ui/components/phone-card-list";
import { SkeletonList, SkeletonTableRows } from "@flrc/ui/components/skeleton";
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
import { cn } from "@flrc/ui/lib/utils";
import { AdminPage } from "../../admin/AdminPage";
import { AuditSkeleton } from "../../admin/page-skeletons";
import { StudentPicker, type PickedStudent } from "../../students/StudentPicker";

export const Route = createFileRoute("/_auth/audit")({ component: AuditPage });

/** Longer values (a teacher comment, say) wrap under a phone card's header, not beside it. */
const INLINE_VALUE_LENGTH = 16;

function oldValue(item: AuditItemOut) {
  // `∅`: the cell had no value before this save; `—`: it held an explicit blank.
  return item.old_existed ? (item.old_value ?? "—") : "∅";
}

/** An entry's old value → new value. `wrap` lets long values break over several lines. */
function ValueChange({
  item,
  className,
  wrap = false,
}: {
  item: AuditItemOut;
  className: string;
  wrap?: boolean;
}) {
  const value = wrap ? "min-w-0 max-w-full break-words whitespace-pre-wrap" : undefined;
  return (
    <span className={cn("tabular items-center gap-1.5 text-xs", className)}>
      <span className={cn("rounded bg-muted px-1.5 py-0.5 text-muted-foreground", value)}>
        {oldValue(item)}
      </span>
      <span className="text-muted-foreground">→</span>
      <span
        className={cn("rounded bg-accent px-1.5 py-0.5 font-medium text-accent-foreground", value)}
      >
        {item.new_value ?? "—"}
      </span>
    </span>
  );
}

function AuditPage() {
  const { t, i18n } = useTranslation();
  const [classId, setClassId] = useState<number>();
  const [actorId, setActorId] = useState<number>();
  const [student, setStudent] = useState<PickedStudent>();
  // Whole calendar days, read like the times the table shows.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [exportPending, setExportPending] = useState(false);
  const {
    data: classes = [],
    isPending: classesPending,
    isError: classesError,
  } = useQuery(listClassesOptions());
  const {
    data: users = [],
    isPending: usersPending,
    isError: usersError,
  } = useQuery(listUsersOptions());
  const filters = {
    class_id: classId,
    actor_id: actorId,
    student_id: student?.id,
    date_from: dateFrom ? `${dateFrom}T00:00:00` : undefined,
    date_to: dateTo ? `${dateTo}T23:59:59.999999` : undefined,
  };
  const filtered = Object.values(filters).some((value) => value !== undefined);
  const audit = useInfiniteQuery({
    queryKey: ["audit", filters],
    queryFn: async ({ pageParam }) => {
      const result = await listAudit({ query: { ...filters, cursor: pageParam } });
      if (result.error) throw result.error;
      if (!result.data) throw new Error("audit_unavailable");
      return result.data;
    },
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    // A filter change keeps the filters (and the table) on screen while the new page loads.
    placeholderData: keepPreviousData,
  });
  const items = audit.data?.pages.flatMap((page) => page.items) ?? [];
  // The export carries exactly the filters the table shows.
  const exportParams = new URLSearchParams(
    Object.entries(filters).flatMap(([key, value]) =>
      value === undefined ? [] : [[key, String(value)]],
    ),
  ).toString();
  const exportUrl = `/api/audit/export.csv${exportParams ? `?${exportParams}` : ""}`;

  function clearFilters() {
    setClassId(undefined);
    setActorId(undefined);
    setStudent(undefined);
    setDateFrom("");
    setDateTo("");
  }

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

  if (classesPending || usersPending || audit.isPending) return <AuditSkeleton />;
  if (classesError || usersError || audit.isError) {
    return <EmptyState title={t("errors.load")} />;
  }

  return (
    <AdminPage
      title={t("audit.title")}
      description={t("audit.description")}
      actions={
        <Button
          variant="outline"
          pending={exportPending}
          pendingLabel={t("audit.exporting")}
          onClick={() => void exportAudit()}
        >
          <DownloadIcon />
          {t("audit.exportCsv")}
        </Button>
      }
    >
      <Card>
        <CardContent className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(5,minmax(0,1fr))_auto]">
          <Field label={t("classes.title")}>
            {(id) => (
              <NativeSelect
                id={id}
                className="w-full"
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
            )}
          </Field>
          <Field label={t("audit.actor")}>
            {(id) => (
              <NativeSelect
                id={id}
                className="w-full"
                value={actorId ?? ""}
                onChange={(event) =>
                  setActorId(event.target.value ? Number(event.target.value) : undefined)
                }
              >
                <option value="">{t("audit.allTeachers")}</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label={t("audit.studentFilter")}>
            {(id) => <StudentPicker id={id} value={student} onChange={setStudent} />}
          </Field>
          <Field label={t("audit.dateFrom")}>
            {(id) => (
              <Input
                id={id}
                className="h-9 rounded-lg max-md:h-10"
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(event) => setDateFrom(event.currentTarget.value)}
              />
            )}
          </Field>
          <Field label={t("audit.dateTo")}>
            {(id) => (
              <Input
                id={id}
                className="h-9 rounded-lg max-md:h-10"
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(event) => setDateTo(event.currentTarget.value)}
              />
            )}
          </Field>
          <Button
            variant="ghost"
            className="max-md:w-full"
            disabled={!filtered}
            onClick={clearFilters}
          >
            <XIcon />
            {t("audit.clearFilters")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardBody className="hidden md:block">
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
                  <TableEmpty colSpan={6}>
                    {filtered ? t("audit.noMatches") : t("audit.empty")}
                  </TableEmpty>
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
                        <ValueChange item={item} className="flex" />
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
                {audit.isFetchingNextPage ? <SkeletonTableRows columns={6} /> : null}
              </TableBody>
            </Table>
          </TableScroll>
        </CardBody>
        {items.length === 0 ? (
          <p className="px-5 py-6 text-sm text-muted-foreground md:hidden">
            {filtered ? t("audit.noMatches") : t("audit.empty")}
          </p>
        ) : (
          <PhoneCardList className="md:hidden" aria-label={t("audit.tableLabel")}>
            {items.map((item) => {
              const long =
                oldValue(item).length > INLINE_VALUE_LENGTH ||
                (item.new_value ?? "").length > INLINE_VALUE_LENGTH;
              return (
                <PhoneCardItem key={item.id} data-testid="audit-card">
                  <PhoneCardHeader
                    title={item.student}
                    subtitle={item.column_label}
                    status={long ? null : <ValueChange item={item} className="inline-flex" />}
                  />
                  {long ? <ValueChange item={item} className="flex flex-wrap" wrap /> : null}
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <p className="min-w-0 break-words">
                      {item.actor} ·{" "}
                      <span className="tabular">
                        {new Date(item.created_at).toLocaleString(i18n.language)}
                      </span>
                    </p>
                    {item.forced || item.via_grant ? (
                      <span className="flex flex-wrap justify-end gap-1">
                        {item.forced ? (
                          <Badge tone="warning">
                            <FlagIcon />
                            {t("audit.forced")}
                          </Badge>
                        ) : null}
                        {item.via_grant ? (
                          <Badge tone="info">
                            <KeyRoundIcon />
                            {t("audit.viaGrant")}
                          </Badge>
                        ) : null}
                      </span>
                    ) : null}
                  </div>
                </PhoneCardItem>
              );
            })}
          </PhoneCardList>
        )}
        {audit.isFetchingNextPage ? (
          <SkeletonList rows={3} className="border-t border-border md:hidden" />
        ) : null}
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
