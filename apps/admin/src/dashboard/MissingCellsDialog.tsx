import { coordinatorMissingCellsOptions, type CompletenessRow } from "@flrc/api-client";
import { buttonVariants } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";
import { LoadingStatus } from "@flrc/ui/components/page-activity";
import { SkeletonTableRows } from "@flrc/ui/components/skeleton";
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
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRightIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

type Subject = "english" | "german" | "french";

/** Which pupil misses which field, and which teacher owns that field. */
export function MissingCellsDialog({
  row,
  yearId,
  semesterId,
  semesterNumber,
  isAdmin,
  onClose,
}: {
  row: CompletenessRow;
  yearId: number;
  semesterId: number;
  semesterNumber: number;
  isAdmin: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const subject = row.subject as Subject;
  const {
    data: cells = [],
    isPending,
    isError,
  } = useQuery(
    coordinatorMissingCellsOptions({
      path: { class_id: row.class_id },
      query: { subject, semester_id: semesterId },
    }),
  );

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {t("adminDashboard.missing.title", {
              class: row.class_name,
              subject: t(`subjects.${subject}`),
            })}
          </DialogTitle>
          <DialogDescription>
            {t("adminDashboard.missing.description", {
              number: semesterNumber,
              count: row.missing_cells,
            })}
          </DialogDescription>
        </DialogHeader>
        {isPending ? <LoadingStatus label={t("loading")} /> : null}
        <div className="overflow-hidden rounded-lg border border-border">
          <TableScroll
            aria-label={t("adminDashboard.missing.tableLabel")}
            className="max-h-[min(55svh,32rem)]"
          >
            <Table className="w-full min-w-[36rem]">
              <TableCaption>{t("adminDashboard.missing.tableLabel")}</TableCaption>
              <TableHead>
                <tr>
                  <TableHeader className="sticky left-0 z-30 min-w-48 border-r bg-muted/95">
                    {t("audit.student")}
                  </TableHeader>
                  <TableHeader className="min-w-40">
                    {t("adminDashboard.missing.field")}
                  </TableHeader>
                  <TableHeader className="min-w-48">
                    {t("adminDashboard.missing.teacher")}
                  </TableHeader>
                </tr>
              </TableHead>
              <TableBody>
                {isPending ? (
                  <SkeletonTableRows columns={3} rows={Math.min(row.missing_cells, 8)} />
                ) : isError ? (
                  <TableEmpty colSpan={3}>{t("errors.load")}</TableEmpty>
                ) : cells.length === 0 ? (
                  <TableEmpty colSpan={3}>{t("adminDashboard.missing.none")}</TableEmpty>
                ) : (
                  cells.map((cell) => (
                    <TableRow key={`${cell.student_id}-${cell.column_id}`}>
                      <TableCell className="sticky left-0 z-10 border-r bg-card group-even:bg-muted group-hover:bg-accent">
                        <span className="flex items-baseline gap-2">
                          <span className="tabular w-10 shrink-0 text-xs text-muted-foreground">
                            {cell.school_number ?? "—"}
                          </span>
                          <TableText className="max-w-44 font-medium">
                            {cell.student_name}
                          </TableText>
                        </span>
                      </TableCell>
                      <TableCell>
                        <TableText className="max-w-56">{cell.field_name}</TableText>
                      </TableCell>
                      <TableCell>
                        <span className="block">
                          {cell.teacher_name ?? (
                            <span className="text-warning">
                              {t("adminDashboard.missing.unassigned")}
                            </span>
                          )}
                        </span>
                        <span className="block text-xs text-muted-foreground">
                          {t(`roles.${cell.owner_role}`)}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableScroll>
        </div>
        {isAdmin ? (
          <DialogFooter>
            <Link
              to="/classes"
              search={{
                year: yearId,
                grade: row.grade_level,
                class: row.class_id,
                subject,
              }}
              className={buttonVariants({ variant: "outline" })}
            >
              {t("adminDashboard.missing.openClass")}
              <ArrowRightIcon />
            </Link>
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
