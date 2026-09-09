import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import {
  ArchiveIcon,
  ArrowRightIcon,
  CalendarDaysIcon,
  ClipboardListIcon,
  FileTextIcon,
  GaugeIcon,
  SchoolIcon,
  UploadIcon,
  UsersIcon,
  KeyRoundIcon,
} from "lucide-react";
import { coordinatorOverviewOptions } from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { PageHeader } from "@flrc/ui/components/page-header";
import { Stat } from "@flrc/ui/components/stat";

export const Route = createFileRoute("/_auth/")({
  component: Dashboard,
});

function Dashboard() {
  const { user } = Route.useRouteContext();
  const { t } = useTranslation();
  const { data: overview } = useQuery(coordinatorOverviewOptions());
  if (user.is_admin) return <Navigate to="/classes" />;

  const destinations = [
    ...(user.is_admin
      ? [
          {
            to: "/students",
            title: t("students.title"),
            description: t("students.description"),
            Icon: UsersIcon,
          },
          {
            to: "/users",
            title: t("users.title"),
            description: t("users.description"),
            Icon: KeyRoundIcon,
          },
          {
            to: "/classes",
            title: t("classes.title"),
            description: t("classes.description"),
            Icon: SchoolIcon,
          },
          {
            to: "/assignments",
            title: t("assignments.title"),
            description: t("assignments.description"),
            Icon: ClipboardListIcon,
          },
          {
            to: "/lifecycle",
            title: t("lifecycle.title"),
            description: t("lifecycle.description"),
            Icon: CalendarDaysIcon,
          },
          {
            to: "/import",
            title: t("import.title"),
            description: t("import.description"),
            Icon: UploadIcon,
          },
        ]
      : []),
    {
      to: "/coordinator",
      title: t("coordinator.title"),
      description: t("adminDashboard.coordinatorDescription"),
      Icon: GaugeIcon,
    },
    {
      to: "/reports",
      title: t("reports.title"),
      description: t("reports.description"),
      Icon: FileTextIcon,
    },
    {
      to: "/archive",
      title: t("archive.title"),
      description: t("archive.description"),
      Icon: ArchiveIcon,
    },
  ];

  return (
    <>
      <PageHeader
        title={t("greeting", { name: user.full_name })}
        description={t("adminDashboard.subtitle")}
        meta={
          overview ? (
            <Badge tone="info">
              {overview.year_label} ·{" "}
              {t("lifecycle.semester", { number: overview.semester_number })}
            </Badge>
          ) : null
        }
      />

      {overview ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat value={overview.students} label={t("coordinator.students")} />
          <Stat value={overview.classes} label={t("coordinator.classes")} />
          <Stat value={overview.active_teachers} label={t("coordinator.teachers")} />
          <Stat
            value={overview.missing_assignments}
            label={t("coordinator.missingAssignments")}
            tone={overview.missing_assignments > 0 ? "warning" : "success"}
          />
        </div>
      ) : null}

      <section>
        <h2 className="font-heading text-sm font-semibold tracking-tight">
          {t("adminDashboard.chooseWorkspace")}
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {destinations.map(({ to, title, description, Icon }) => (
            <Link
              key={to}
              to={to}
              className="group flex gap-3 rounded-xl border border-border bg-card p-4 shadow-card outline-none transition-colors hover:border-primary/35 hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring/50"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:bg-card group-hover:text-primary">
                <Icon className="size-4.5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="font-heading block font-semibold tracking-tight">{title}</span>
                <span className="mt-0.5 block text-sm leading-5 text-muted-foreground">
                  {description}
                </span>
              </span>
              <ArrowRightIcon className="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
