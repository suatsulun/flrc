import type { ReportReadiness } from "@flrc/api-client";
import { Card, CardDescription, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Link } from "@tanstack/react-router";
import { ArrowRightIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CompletionBar } from "./CompletionBar";

/** How complete the grades behind each report card are, per card kind. */
export function ReadinessCard({
  readiness,
  semesterNumber,
}: {
  readiness: ReportReadiness[];
  semesterNumber: number;
}) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <div className="min-w-0">
          <CardTitle>{t("adminDashboard.readiness.title")}</CardTitle>
          <CardDescription>
            {t("adminDashboard.readiness.description", { number: semesterNumber })}
          </CardDescription>
        </div>
        <Link
          to="/reports"
          className="inline-flex items-center gap-1 text-xs font-medium text-primary-strong hover:underline"
        >
          {t("reports.title")}
          <ArrowRightIcon className="size-3.5" />
        </Link>
      </CardHeader>
      <ul className="divide-y divide-border border-t border-border">
        {readiness.map((item) => (
          <li key={item.kind} className="grid gap-1.5 px-5 py-3">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <span className="text-sm font-medium">{t(`reports.kinds.${item.kind}`)}</span>
              <span className="text-xs text-muted-foreground">
                {item.eligible_classes === 0
                  ? t("adminDashboard.readiness.noStudents")
                  : t("adminDashboard.readiness.classes", {
                      complete: item.complete_classes,
                      eligible: item.eligible_classes,
                      students: item.students,
                    })}
              </span>
            </div>
            {item.eligible_classes > 0 ? <CompletionBar percent={item.percent} /> : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}
