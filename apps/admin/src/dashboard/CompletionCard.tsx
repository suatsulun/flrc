import type { CompletenessRow, CompletionSummary } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@flrc/ui/components/card";
import {
  PhoneCardActions,
  PhoneCardHeader,
  PhoneCardItem,
  PhoneCardList,
} from "@flrc/ui/components/phone-card-list";
import { Segmented } from "@flrc/ui/components/segmented";
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
} from "@flrc/ui/components/table";
import { ListChecksIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CompletionBar } from "./CompletionBar";
import { formatPercent } from "./format";
import { MissingCellsDialog } from "./MissingCellsDialog";

type Filter = "incomplete" | "all";

/** Grade completion per class and subject, with a drill-down into every empty cell. */
export function CompletionCard({
  completion,
  yearId,
  isAdmin,
}: {
  completion: CompletionSummary;
  yearId: number;
  isAdmin: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [filter, setFilter] = useState<Filter>("incomplete");
  const [selected, setSelected] = useState<CompletenessRow>();
  // A subject nobody in the class takes has no grid; it is neither complete nor missing. A grid
  // with pupils but no fields is unfinished: it has nothing to fill yet.
  const taught = completion.rows.filter((row) => row.roster_count > 0);
  const rows =
    filter === "all"
      ? taught
      : taught.filter((row) => row.expected_cells === 0 || row.missing_cells > 0);

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <div className="min-w-0">
          <CardTitle>{t("adminDashboard.completion.title")}</CardTitle>
          <CardDescription>
            {completion.percent === null
              ? t("adminDashboard.completion.noFields", { number: completion.semester_number })
              : t("adminDashboard.completion.overall", {
                  number: completion.semester_number,
                  percent: formatPercent(completion.percent, i18n.language),
                  missing: completion.missing_cells,
                })}
          </CardDescription>
        </div>
        <Segmented
          ariaLabel={t("adminDashboard.completion.filter")}
          options={[
            { value: "incomplete", label: t("adminDashboard.completion.incomplete") },
            { value: "all", label: t("adminDashboard.completion.all") },
          ]}
          value={filter}
          onChange={setFilter}
        />
      </CardHeader>
      <CardBody className="hidden md:block">
        <TableScroll aria-label={t("coordinator.tableLabel")}>
          <Table className="w-full min-w-[52rem]">
            <TableCaption>{t("coordinator.tableLabel")}</TableCaption>
            <TableHead>
              <tr>
                <TableHeader className="sticky left-0 z-30 min-w-28 border-r bg-muted/95">
                  {t("classes.title")}
                </TableHeader>
                <TableHeader className="min-w-28">{t("grid.subject")}</TableHeader>
                <TableHeader className="w-24" align="right">
                  {t("coordinator.expected")}
                </TableHeader>
                <TableHeader className="w-24" align="right">
                  {t("coordinator.filled")}
                </TableHeader>
                <TableHeader className="w-24" align="right">
                  {t("coordinator.missing")}
                </TableHeader>
                <TableHeader className="w-56">{t("coordinator.completion")}</TableHeader>
                <TableHeader className="w-44">
                  <span className="sr-only">{t("adminDashboard.completion.details")}</span>
                </TableHeader>
              </tr>
            </TableHead>
            <TableBody>
              {rows.length === 0 ? (
                <TableEmpty colSpan={7}>
                  {taught.length === 0
                    ? t("coordinator.empty")
                    : t("adminDashboard.completion.allComplete")}
                </TableEmpty>
              ) : (
                rows.map((row) => (
                  <TableRow key={`${row.class_id}-${row.subject}`}>
                    <TableCell className="sticky left-0 z-10 border-r bg-card font-medium group-even:bg-muted group-hover:bg-accent">
                      {row.class_name}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {t(`subjects.${row.subject}`)}
                    </TableCell>
                    <TableCell align="right">{row.expected_cells}</TableCell>
                    <TableCell align="right">{row.filled_cells}</TableCell>
                    <TableCell
                      align="right"
                      className={row.missing_cells > 0 ? "font-medium text-warning" : undefined}
                    >
                      {row.missing_cells}
                    </TableCell>
                    <TableCell>
                      <CompletionBar percent={row.expected_cells === 0 ? null : row.percent} />
                    </TableCell>
                    <TableCell align="right">
                      {row.missing_cells > 0 ? (
                        <Button variant="ghost" size="sm" onClick={() => setSelected(row)}>
                          <ListChecksIcon />
                          {t("adminDashboard.completion.details")}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableScroll>
      </CardBody>
      {rows.length === 0 ? (
        <p className="px-5 py-6 text-sm text-muted-foreground md:hidden">
          {taught.length === 0
            ? t("coordinator.empty")
            : t("adminDashboard.completion.allComplete")}
        </p>
      ) : (
        <PhoneCardList className="md:hidden" aria-label={t("coordinator.tableLabel")}>
          {rows.map((row) => (
            <PhoneCardItem key={`${row.class_id}-${row.subject}`} data-testid="completion-card">
              <PhoneCardHeader
                title={`${row.class_name} · ${t(`subjects.${row.subject}`)}`}
                status={
                  // Nothing expected yet is not "complete": like the bar, it shows no verdict.
                  row.expected_cells === 0 ? null : (
                    <Badge tone={row.missing_cells > 0 ? "warning" : "success"}>
                      {row.missing_cells > 0
                        ? `${t("coordinator.missing")}: ${row.missing_cells}`
                        : formatPercent(100, i18n.language)}
                    </Badge>
                  )
                }
              />
              <div className="space-y-2">
                <CompletionBar percent={row.expected_cells === 0 ? null : row.percent} />
                <p className="tabular flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    {t("coordinator.expected")}:{" "}
                    <strong className="font-medium text-foreground">{row.expected_cells}</strong>
                  </span>
                  <span>
                    {t("coordinator.filled")}:{" "}
                    <strong className="font-medium text-foreground">{row.filled_cells}</strong>
                  </span>
                  <span className={row.missing_cells > 0 ? "font-medium text-warning" : undefined}>
                    {t("coordinator.missing")}: <strong>{row.missing_cells}</strong>
                  </span>
                </p>
              </div>
              {row.missing_cells > 0 ? (
                <PhoneCardActions>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => setSelected(row)}
                  >
                    <ListChecksIcon />
                    {t("adminDashboard.completion.details")}
                  </Button>
                </PhoneCardActions>
              ) : null}
            </PhoneCardItem>
          ))}
        </PhoneCardList>
      )}
      {selected ? (
        <MissingCellsDialog
          row={selected}
          yearId={yearId}
          semesterId={completion.semester_id}
          semesterNumber={completion.semester_number}
          isAdmin={isAdmin}
          onClose={() => setSelected(undefined)}
        />
      ) : null}
    </Card>
  );
}
