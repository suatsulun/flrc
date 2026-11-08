import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { TablePropertiesIcon } from "lucide-react";
import { listAcademicYearsOptions, listClassCatalogOptions } from "@flrc/api-client";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { GridPageSkeleton } from "../../page-skeletons";

export const Route = createFileRoute("/_auth/")({ component: TableHome });

function TableHome() {
  const { t } = useTranslation();
  const {
    data: years = [],
    isPending: yearsPending,
    isError: yearsError,
  } = useQuery(listAcademicYearsOptions());
  const current =
    years.find((item) => item.status === "active") ??
    [...years].sort((left, right) => right.label.localeCompare(left.label))[0];
  const semester =
    current?.semesters.find((item) => item.status === "open")?.number ??
    current?.semesters[0]?.number ??
    1;
  const {
    data: catalog = [],
    isLoading: catalogLoading,
    isError: catalogError,
  } = useQuery({
    ...listClassCatalogOptions({ query: { year_id: current?.id, semester } }),
    enabled: Boolean(current),
  });

  // The start page opens the first grade grid, so it loads in the grid's shape.
  if (yearsPending || catalogLoading) return <GridPageSkeleton />;
  if (yearsError || catalogError) return <EmptyState title={t("errors.load")} />;

  const boards = catalog.flatMap((schoolClass) =>
    schoolClass.subjects.map((subject) => ({ schoolClass, subject })),
  );
  const first = boards.find((item) => item.subject.can_write) ?? boards[0];
  if (first) {
    return (
      <Navigate
        replace
        to="/classes/$classId/$subject"
        params={{
          classId: String(first.schoolClass.id),
          subject: first.subject.subject,
        }}
        search={{ semester }}
      />
    );
  }

  return (
    <EmptyState
      icon={<TablePropertiesIcon />}
      title={t("grid.emptyTitle")}
      description={t("grid.emptyBody")}
    />
  );
}
