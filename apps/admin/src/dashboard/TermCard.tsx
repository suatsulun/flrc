import type { NextStep, TermStatus } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { buttonVariants } from "@flrc/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Link } from "@tanstack/react-router";
import type { TFunction } from "i18next";
import { ArrowRightIcon, CircleAlertIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CompletionBar } from "./CompletionBar";
import { formatPercent } from "./format";

function stepText(t: TFunction, step: NextStep, term: TermStatus, language: string) {
  const year = term.year_label ?? "";
  switch (step.code) {
    case "create_year":
      return {
        title: t("adminDashboard.steps.createYear.title"),
        body: t("adminDashboard.steps.createYear.body"),
      };
    case "activate_year":
      return {
        title: t("adminDashboard.steps.activateYear.title", { year }),
        body: step.blockers.length
          ? t("lifecycle.missingNumbers", { count: step.blockers[0]!.count })
          : t("adminDashboard.steps.activateYear.ready"),
      };
    case "collect_grades":
      return {
        title: t("adminDashboard.steps.collectGrades.title", { number: step.semester_number }),
        body:
          step.completion_percent === null
            ? t("adminDashboard.steps.collectGrades.noFields")
            : step.blockers.length
              ? t("adminDashboard.steps.collectGrades.withoutFields", {
                  count: step.blockers[0]!.count,
                })
              : t("adminDashboard.steps.collectGrades.body", {
                  percent: formatPercent(step.completion_percent, language),
                  missing: step.missing_cells,
                }),
      };
    case "advance_semester":
      return {
        title: t("adminDashboard.steps.advanceSemester.title"),
        body: t("adminDashboard.steps.advanceSemester.body"),
      };
    case "lock_semester":
      return {
        title: t("adminDashboard.steps.lockSemester.title"),
        body: t("adminDashboard.steps.lockSemester.body"),
      };
    case "close_year":
      return {
        title: t("adminDashboard.steps.closeYear.title", { year }),
        body: t("adminDashboard.steps.closeYear.body"),
      };
  }
}

/** Where the school year stands, the next lifecycle step and why. */
export function TermCard({
  term,
  step,
  isAdmin,
}: {
  term: TermStatus;
  step: NextStep;
  isAdmin: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { title, body } = stepText(t, step, term, i18n.language);
  const blocked = step.blockers.length > 0;

  return (
    <Card>
      <CardHeader>
        <div className="min-w-0">
          <CardTitle>{t("adminDashboard.term.title")}</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            {term.year_label ?? t("adminDashboard.term.noYear")}
          </p>
        </div>
        {term.year_status ? (
          <Badge tone={term.year_status === "active" ? "success" : "warning"}>
            {t(`lifecycle.${term.year_status}`)}
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {term.semesters.length ? (
          <ul className="flex flex-wrap gap-2" aria-label={t("adminDashboard.term.semesters")}>
            {term.semesters.map((semester) => (
              <li key={semester.id}>
                <Badge tone={semester.status === "open" ? "info" : "neutral"}>
                  {t("lifecycle.semester", { number: semester.number })} ·{" "}
                  {t(`lifecycle.${semester.status === "open" ? "open" : "locked"}`)}
                </Badge>
              </li>
            ))}
          </ul>
        ) : null}

        <div
          className={`rounded-lg border p-4 ${
            blocked ? "border-warning/40 bg-warning-surface" : "border-border bg-muted/40"
          }`}
        >
          <p className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
            {t("adminDashboard.term.nextStep")}
          </p>
          <p className="mt-1 font-heading font-semibold tracking-tight">{title}</p>
          <p className="mt-1 flex gap-1.5 text-sm leading-6 text-muted-foreground">
            {blocked ? <CircleAlertIcon className="mt-1 size-4 shrink-0 text-warning" /> : null}
            <span>{body}</span>
          </p>
          {step.code === "collect_grades" && step.completion_percent !== null ? (
            <div className="mt-3">
              <CompletionBar percent={step.completion_percent} />
            </div>
          ) : null}
        </div>

        {isAdmin ? (
          <Link to="/lifecycle" className={buttonVariants({ variant: "outline", size: "sm" })}>
            {t("adminDashboard.term.openLifecycle")}
            <ArrowRightIcon />
          </Link>
        ) : null}
      </CardContent>
    </Card>
  );
}
