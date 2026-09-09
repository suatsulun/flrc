import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { UploadIcon } from "lucide-react";
import { listYearsOptions } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Field } from "@flrc/ui/components/field";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { PageSkeleton } from "@flrc/ui/components/page-activity";
import { AdminPage } from "../../admin/AdminPage";
import { ImportReview } from "../../imports/ImportReview";

export const Route = createFileRoute("/_auth/import")({ component: ImportPage });

function ImportPage() {
  const { t } = useTranslation();
  const { data: years = [], isPending, isError } = useQuery(listYearsOptions());
  const [yearId, setYearId] = useState<number>();
  const selectedYear =
    years.find((year) => year.id === yearId) ??
    years.find((year) => year.status === "setup") ??
    years.find((year) => year.status === "active");
  const [file, setFile] = useState<File>();
  const [reviewId, setReviewId] = useState<string>();
  const [committing, setCommitting] = useState(false);

  if (isPending) return <PageSkeleton />;
  if (isError) return <EmptyState title={t("errors.load")} />;

  return (
    <AdminPage title={t("import.title")} description={t("import.description")}>
      <Card>
        <CardHeader>
          <CardTitle>{t("import.step1")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-[12rem_minmax(0,1fr)_auto] sm:items-end">
            <Field label={t("reports.yearLabel")}>
              {(id) => (
                <NativeSelect
                  id={id}
                  className="w-full"
                  disabled={committing}
                  value={selectedYear?.id ?? ""}
                  onChange={(event) => {
                    setYearId(Number(event.target.value));
                    setReviewId(undefined);
                  }}
                >
                  {years
                    .filter((year) => year.status !== "archived")
                    .map((year) => (
                      <option key={year.id} value={year.id}>
                        {year.label}
                      </option>
                    ))}
                </NativeSelect>
              )}
            </Field>
            <Field label={t("import.file")}>
              {(id) => (
                <input
                  id={id}
                  accept=".xlsx"
                  type="file"
                  disabled={committing}
                  className="h-9 w-full cursor-pointer rounded-lg border border-input bg-card text-sm shadow-card file:mr-3 file:h-full file:cursor-pointer file:border-0 file:bg-muted file:px-3 file:text-sm file:font-medium"
                  onChange={(event) => {
                    setFile(event.target.files?.[0]);
                    setReviewId(undefined);
                  }}
                />
              )}
            </Field>
            <Button
              disabled={!file || !selectedYear || committing}
              onClick={() => setReviewId(crypto.randomUUID())}
            >
              <UploadIcon />
              {t("import.preview")}
            </Button>
          </div>
          {!selectedYear ? (
            <p className="mt-3 text-sm text-muted-foreground">{t("import.noYear")}</p>
          ) : null}
        </CardContent>
      </Card>
      {reviewId && file && selectedYear ? (
        <ImportReview
          key={reviewId}
          reviewId={reviewId}
          file={file}
          yearId={selectedYear.id}
          yearLabel={selectedYear.label}
          onCommittingChange={setCommitting}
        />
      ) : null}
    </AdminPage>
  );
}
