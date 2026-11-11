import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { listAcademicYearsOptions, listJobsQueryKey } from "@flrc/api-client";
import { AcademicContextBar } from "@flrc/ui/components/academic-context-bar";
import { Button } from "@flrc/ui/components/button";
import { Card, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Field } from "@flrc/ui/components/field";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { Segmented } from "@flrc/ui/components/segmented";
import { academicContextLabels } from "@flrc/i18n";
import { AdminPage } from "../../admin/AdminPage";
import { ReportsSkeleton } from "../../admin/page-skeletons";
import { PdfLeaveGuard } from "../../admin/PdfLeaveGuard";
import { DownloadsList } from "../../reports/DownloadsList";
import { ReportKindCard } from "../../reports/ReportKindCard";
import { reportRequestMessage } from "../../reports/report-errors";
import {
  REPORT_KINDS,
  startReportJob,
  startYearExport,
  type JobScope,
  type ReportFormat,
  type ReportKind,
  type ReportLocale,
  type ReportPeriod,
} from "../../reports/report-requests";
import { useDirectDownload } from "../../reports/use-direct-download";

const LOCALES = [
  { value: "tr", label: "TR", title: "Türkçe" },
  { value: "en", label: "EN", title: "English" },
  { value: "de", label: "DE", title: "Deutsch" },
  { value: "fr", label: "FR", title: "Français" },
] as const;

export const Route = createFileRoute("/_auth/reports")({ component: ReportsPage });

function ReportsPage() {
  const { user } = Route.useRouteContext();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: years = [], isPending: yearsPending } = useQuery(listAcademicYearsOptions());
  const [yearId, setYearId] = useState<number>();
  const [semesterNumber, setSemesterNumber] = useState<number>();
  const [locale, setLocale] = useState<ReportLocale>("tr");
  const [exportPending, setExportPending] = useState(false);
  const direct = useDirectDownload();

  const activeYearId = yearId ?? years.find((year) => year.status === "active")?.id ?? years[0]?.id;
  const selectedYear = years.find((year) => year.id === activeYearId);
  const selectedSemester =
    selectedYear?.semesters.find((term) => term.number === semesterNumber) ??
    selectedYear?.semesters.find((term) => term.status === "open") ??
    selectedYear?.semesters[0];

  async function startJob(
    kind: ReportKind,
    format: ReportFormat,
    scope: JobScope,
    period?: ReportPeriod,
  ) {
    if (!selectedSemester) return false;
    try {
      await startReportJob(selectedSemester.id, kind, locale, format, scope, period);
      toast.success(t("reports.jobQueued"));
      return true;
    } catch (error) {
      toast.error(reportRequestMessage(t, error));
      return false;
    } finally {
      void queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
    }
  }

  async function exportYear() {
    if (!activeYearId) return;
    setExportPending(true);
    try {
      await startYearExport(activeYearId);
      toast.success(t("reports.exportQueued"));
    } catch (error) {
      toast.error(reportRequestMessage(t, error));
    } finally {
      setExportPending(false);
      void queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
    }
  }

  if (yearsPending) return <ReportsSkeleton />;

  return (
    <AdminPage
      title={t("reports.title")}
      description={t("reports.description")}
      actions={
        <Field label={t("reports.languageLabel")}>
          {() => (
            <Segmented
              ariaLabel={t("reports.languageLabel")}
              options={LOCALES}
              value={locale}
              onChange={setLocale}
              size="sm"
            />
          )}
        </Field>
      }
    >
      <PdfLeaveGuard active={direct.pending !== null} onLeave={direct.stop} />
      {selectedYear ? (
        <AcademicContextBar
          years={years}
          yearId={selectedYear.id}
          semesterNumber={selectedSemester?.number ?? 1}
          onYearChange={(next) => {
            setYearId(next);
            setSemesterNumber(undefined);
          }}
          onSemesterChange={setSemesterNumber}
          labels={academicContextLabels(t, t("classWorkspace.readOnly"))}
        />
      ) : null}
      <p className="text-sm text-muted-foreground">{t("reports.deliveryHint")}</p>
      <div className="grid gap-3 md:grid-cols-2">
        {REPORT_KINDS.map((kind) => (
          <ReportKindCard
            key={kind}
            kind={kind}
            semesterId={selectedSemester?.id}
            locale={locale}
            demo={Boolean(user.demo)}
            direct={direct}
            onStartJob={startJob}
          />
        ))}
      </div>

      {user.is_admin ? (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("reports.yearExport")}</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">{t("reports.exportDescription")}</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <Field label={t("reports.yearLabel")}>
                {(id) => (
                  <NativeSelect
                    id={id}
                    className="w-40"
                    value={activeYearId ?? ""}
                    onChange={(event) => setYearId(Number(event.target.value))}
                  >
                    {years.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Button
                variant="outline"
                disabled={!activeYearId}
                pending={exportPending}
                pendingLabel={t("reports.starting")}
                onClick={() => void exportYear()}
              >
                {t("reports.export")}
              </Button>
            </div>
          </CardHeader>
        </Card>
      ) : null}

      <DownloadsList />
    </AdminPage>
  );
}
