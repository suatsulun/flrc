import { roleLabel } from "@flrc/i18n";
import type { SetupProblems } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Link } from "@tanstack/react-router";
import { ArrowRightIcon, CircleCheckIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ClassWorkspaceSearch } from "../routes/_auth/classes";

/** Items shown per problem; the rest are counted and fixed on the linked page. */
const VISIBLE_ITEMS = 6;

type Item = { key: string; label: string; to?: ClassWorkspaceSearch };
type Group = {
  key: string;
  label: string;
  count: number;
  items: Item[];
  /** The page that fixes every item of this problem, when there is one. */
  fix?: ReactNode;
};

const chipClass =
  "inline-flex max-w-full items-center truncate rounded-md border border-border bg-background px-2 py-0.5 text-xs";

/** Setup gaps with the concrete classes, teachers and pupils, each linked to where it is fixed. */
export function SetupProblemsCard({
  problems,
  yearId,
  isAdmin,
}: {
  problems: SetupProblems;
  yearId: number;
  isAdmin: boolean;
}) {
  const { t } = useTranslation();
  const fixLink = (to: "/assignments" | "/users") => (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-xs font-medium text-primary-strong hover:underline"
    >
      {t("adminDashboard.problems.fix")}
      <ArrowRightIcon className="size-3.5" />
    </Link>
  );
  const groups: Group[] = [
    {
      key: "roles",
      label: t("adminDashboard.problems.unassignedRoles"),
      count: problems.unassigned_roles.count,
      items: problems.unassigned_roles.items.map((gap) => ({
        key: `${gap.class_id}-${gap.role}`,
        label: `${gap.class_name} · ${roleLabel(t, gap.role, gap.grade_level)}`,
        to: { year: yearId, grade: gap.grade_level, class: gap.class_id },
      })),
      fix: fixLink("/assignments"),
    },
    {
      key: "fields",
      label: t("adminDashboard.problems.classesWithoutFields"),
      count: problems.classes_without_fields.count,
      items: problems.classes_without_fields.items.map((gap) => ({
        key: `${gap.class_id}-${gap.subject}`,
        label: `${gap.class_name} · ${t(`subjects.${gap.subject}`)}`,
        to: { year: yearId, grade: gap.grade_level, class: gap.class_id, subject: gap.subject },
      })),
    },
    {
      key: "reportName",
      label: t("adminDashboard.problems.teachersWithoutReportName"),
      count: problems.teachers_without_report_name.count,
      items: problems.teachers_without_report_name.items.map((teacher) => ({
        key: String(teacher.user_id),
        label: teacher.full_name,
      })),
      fix: fixLink("/users"),
    },
    {
      key: "signature",
      label: t("adminDashboard.problems.teachersWithoutSignature"),
      count: problems.teachers_without_signature.count,
      items: problems.teachers_without_signature.items.map((teacher) => ({
        key: String(teacher.user_id),
        label: teacher.full_name,
      })),
      fix: fixLink("/users"),
    },
    ...(
      [
        [
          "number",
          t("adminDashboard.problems.studentsWithoutNumber"),
          problems.students_without_number,
        ],
        [
          "language",
          t("adminDashboard.problems.studentsWithoutLanguage"),
          problems.students_without_language,
        ],
      ] as const
    ).map(([key, label, gaps]) => ({
      key,
      label,
      count: gaps.count,
      items: gaps.items.map((student) => ({
        key: String(student.student_id),
        label: `${student.class_name} · ${student.full_name}`,
        to: { year: yearId, grade: student.grade_level, class: student.class_id },
      })),
    })),
  ].filter((group) => group.count > 0);

  return (
    <Card>
      <CardHeader>
        <div className="min-w-0">
          <CardTitle>{t("adminDashboard.problems.title")}</CardTitle>
          <CardDescription>{t("adminDashboard.problems.description")}</CardDescription>
        </div>
        {groups.length ? (
          <Badge tone="warning">{groups.reduce((total, group) => total + group.count, 0)}</Badge>
        ) : null}
      </CardHeader>
      {groups.length === 0 ? (
        <p className="flex items-center gap-2 border-t border-border px-5 py-6 text-sm text-muted-foreground">
          <CircleCheckIcon className="size-4 text-success" />
          {t("adminDashboard.problems.none")}
        </p>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {groups.map((group) => {
            const shown = group.items.slice(0, VISIBLE_ITEMS);
            const hidden = group.count - shown.length;
            return (
              <li key={group.key} className="space-y-2 px-5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                    <Badge tone="warning" className="tabular">
                      {group.count}
                    </Badge>
                    <span className="truncate">{group.label}</span>
                  </span>
                  {isAdmin ? group.fix : null}
                </div>
                <ul className="flex flex-wrap gap-1.5">
                  {shown.map((item) => (
                    <li key={item.key} className="min-w-0 max-w-full">
                      {isAdmin && item.to ? (
                        <Link
                          to="/classes"
                          search={item.to}
                          className={`${chipClass} text-primary-strong hover:border-primary/35 hover:bg-accent/40`}
                        >
                          {item.label}
                        </Link>
                      ) : (
                        <span className={`${chipClass} text-muted-foreground`}>{item.label}</span>
                      )}
                    </li>
                  ))}
                  {hidden > 0 ? (
                    <li className="px-1 py-0.5 text-xs text-muted-foreground">
                      {t("adminDashboard.problems.more", { count: hidden })}
                    </li>
                  ) : null}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
