import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { DownloadIcon, ExternalLinkIcon, FileTextIcon, UsersIcon } from "lucide-react";
import { getReportRosterOptions } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardContent } from "@flrc/ui/components/card";
import { Field } from "@flrc/ui/components/field";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { Segmented } from "@flrc/ui/components/segmented";
import { Skeleton } from "@flrc/ui/components/skeleton";
import {
  planDelivery,
  reportFormatOptions,
  reportPdfUrl,
  type JobScope,
  type ReportFormat,
  type ReportKind,
  type ReportLocale,
  type ReportPeriod,
} from "./report-requests";
import { ReportPeriodPicker } from "./ReportPeriodPicker";
import { StudentPickerDialog } from "./StudentPickerDialog";
import type { DirectDownload } from "./use-direct-download";

/**
 * One card kind: view or download one class at once, prepare the whole school as a background
 * job in the chosen format, or pick students across classes.
 */
export function ReportKindCard({
  kind,
  semesterId,
  locale,
  demo,
  direct,
  onStartJob,
}: {
  kind: ReportKind;
  semesterId: number | undefined;
  locale: ReportLocale;
  demo: boolean;
  direct: DirectDownload;
  onStartJob: (
    kind: ReportKind,
    format: ReportFormat,
    scope: JobScope,
    period?: ReportPeriod,
  ) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const {
    data: roster = [],
    isLoading: rosterLoading,
    isFetching,
  } = useQuery({
    ...getReportRosterOptions({ query: { semester_id: semesterId ?? 0, kind } }),
    enabled: semesterId !== undefined,
  });
  const [classId, setClassId] = useState<number>();
  const [format, setFormat] = useState<ReportFormat>("combined");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [jobPending, setJobPending] = useState<"school" | "picker" | null>(null);
  const [period, setPeriod] = useState<ReportPeriod>({ startMonth: 9, endMonth: 11 });
  const reportPeriod = kind === "english_middle" ? period : undefined;

  const selectedClass = roster.find((item) => item.id === classId) ?? roster[0];
  const busy = direct.pending !== null;
  const classKey = `${kind}:class`;
  const pickerKey = `${kind}:picker`;
  const unavailable = semesterId === undefined || isFetching || !selectedClass;

  function openClass(action: "view" | "download") {
    if (semesterId === undefined || !selectedClass) return;
    void direct.run(
      classKey,
      action,
      reportPdfUrl(semesterId, kind, locale, { classId: selectedClass.id }, reportPeriod),
    );
  }

  async function startJob(source: "school" | "picker", jobFormat: ReportFormat, scope: JobScope) {
    setJobPending(source);
    try {
      return await onStartJob(kind, jobFormat, scope, reportPeriod);
    } finally {
      setJobPending(null);
    }
  }

  async function submitPicker(selected: ReadonlySet<number>, pickerFormat: ReportFormat) {
    if (semesterId === undefined) return;
    const plan = planDelivery(roster, selected, pickerFormat);
    const delivered =
      "direct" in plan
        ? await direct.run(
            pickerKey,
            "download",
            reportPdfUrl(semesterId, kind, locale, plan.direct, reportPeriod),
          )
        : await startJob("picker", pickerFormat, plan.job);
    if (delivered) setPickerOpen(false);
  }

  const students = roster.reduce((sum, item) => sum + item.students.length, 0);

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col gap-4">
        <div>
          <div className="flex items-start justify-between gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
              <FileTextIcon className="size-4.5" />
            </span>
            <Badge tone="outline">{t(`reports.setScopes.${kind}`)}</Badge>
          </div>
          <h3 className="font-heading mt-3 font-semibold tracking-tight">
            {t(`reports.kinds.${kind}`)}
          </h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {t(`reports.setDescriptions.${kind}`)}
          </p>
        </div>

        {kind === "english_middle" ? (
          <ReportPeriodPicker
            value={period}
            onChange={setPeriod}
            disabled={busy || jobPending !== null}
          />
        ) : null}

        {semesterId !== undefined && !isFetching && roster.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("reports.noEligibleClasses")}</p>
        ) : null}

        <div className="grid gap-2">
          <Field label={t("reports.classLabel")}>
            {(id) =>
              rosterLoading ? (
                <Skeleton className="h-9 w-full" />
              ) : (
                <NativeSelect
                  id={id}
                  value={selectedClass?.id ?? ""}
                  disabled={unavailable || busy}
                  onChange={(event) => setClassId(Number(event.target.value))}
                >
                  {roster.map((item) => (
                    <option key={item.id} value={item.id}>
                      {t("reports.classOption", { name: item.name, count: item.students.length })}
                    </option>
                  ))}
                </NativeSelect>
              )
            }
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={unavailable || busy}
              pending={direct.pending?.key === classKey && direct.pending.action === "view"}
              pendingLabel={t("reports.generatingPdf")}
              onClick={() => openClass("view")}
            >
              <ExternalLinkIcon />
              {t("reports.view")}
            </Button>
            <Button
              size="sm"
              disabled={unavailable || busy}
              pending={direct.pending?.key === classKey && direct.pending.action === "download"}
              pendingLabel={t("reports.generatingPdf")}
              onClick={() => openClass("download")}
            >
              <DownloadIcon />
              {t("reports.download")}
            </Button>
          </div>
        </div>

        <div className="mt-auto grid gap-3 border-t border-border pt-4">
          {demo ? null : (
            <div className="grid gap-2">
              {rosterLoading ? (
                <Skeleton className="h-4 w-48 max-w-full rounded-md" />
              ) : (
                <p className="text-[0.8125rem] font-medium">
                  {t("reports.wholeSchool", { count: students })}
                </p>
              )}
              <Segmented
                ariaLabel={t("reports.formatLabel")}
                options={reportFormatOptions(t)}
                value={format}
                onChange={setFormat}
                size="sm"
              />
              <Button
                size="sm"
                variant="outline"
                className="self-start"
                disabled={unavailable}
                pending={jobPending === "school"}
                pendingLabel={t("reports.starting")}
                onClick={() => void startJob("school", format, { classIds: [], studentIds: [] })}
              >
                {t("reports.prepareWholeSchool")}
              </Button>
            </div>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="self-start"
            disabled={unavailable}
            onClick={() => setPickerOpen(true)}
          >
            <UsersIcon />
            {t("reports.pickStudents")}
          </Button>
        </div>
      </CardContent>
      <StudentPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        title={t("reports.picker.title", { kind: t(`reports.kinds.${kind}`) })}
        roster={roster}
        demo={demo}
        pending={jobPending === "picker" || direct.pending?.key === pickerKey}
        onSubmit={(selected, pickerFormat) => void submitPicker(selected, pickerFormat)}
      />
    </Card>
  );
}
