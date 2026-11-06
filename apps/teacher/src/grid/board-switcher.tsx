import { academicContextLabels, gradeTabLabel } from "@flrc/i18n";
import { listAcademicYearsOptions, listClassCatalogOptions } from "@flrc/api-client";
import { AcademicContextBar } from "@flrc/ui/components/academic-context-bar";
import { Segmented } from "@flrc/ui/components/segmented";
import { usePrefetchSiblings } from "@flrc/ui/hooks/use-prefetch-siblings";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { Subject } from "./subjects";

/**
 * Year, semester, grade, subject and class pickers for a class board. The grid and
 * the class report share it, so moving between classes works the same in both;
 * each view navigates to its own route and may narrow the grades and subjects.
 */
export function BoardSwitcher({
  classId,
  subject,
  requestedSemester,
  meta,
  grades,
  subjects,
  compact,
  lockedLabel,
  goTo,
  prefetchBoard,
}: {
  classId: string;
  subject: Subject;
  /** The semester in the URL; undefined lets the server pick the open one. */
  requestedSemester: number | undefined;
  meta: { year_id: number; grade_level: number; semester_number: number };
  /** The grades this view offers; a single subject hides the subject picker. */
  grades: readonly number[];
  subjects: readonly Subject[];
  compact: boolean;
  lockedLabel: string;
  goTo: (classId: number, subject: Subject, semester: number) => Promise<void>;
  /** Warms the target view's data for a sibling class before the teacher clicks it. */
  prefetchBoard: (classId: number) => Promise<void>;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: years = [] } = useQuery(listAcademicYearsOptions());
  const { data: catalog = [] } = useQuery(
    listClassCatalogOptions({
      query: { year_id: meta.year_id, semester: requestedSemester },
    }),
  );
  const gradeTabs = useMemo(
    () =>
      catalog.filter(
        (item) =>
          item.grade_level === meta.grade_level &&
          item.subjects.some((candidate) => candidate.subject === subject),
      ),
    [catalog, meta.grade_level, subject],
  );

  usePrefetchSiblings(gradeTabs, prefetchBoard);

  const goToBoard = (nextGrade: number, nextSubject: Subject) => {
    const target = catalog.find(
      (item) =>
        item.grade_level === nextGrade &&
        item.subjects.some((candidate) => candidate.subject === nextSubject),
    );
    if (!target) return;
    void goTo(target.id, nextSubject, meta.semester_number);
  };

  const switchYear = async (nextYearId: number) => {
    const nextYear = years.find((item) => item.id === nextYearId);
    if (!nextYear) return;
    const nextSemester =
      nextYear.semesters.find((item) => item.number === meta.semester_number)?.number ??
      nextYear.semesters.find((item) => item.status === "open")?.number ??
      nextYear.semesters[0]?.number ??
      1;
    const nextCatalog = await queryClient.fetchQuery(
      listClassCatalogOptions({
        query: { year_id: nextYearId, semester: nextSemester },
      }),
    );
    const current = catalog.find((item) => item.id === Number(classId));
    const offered = nextCatalog.filter(
      (item) =>
        grades.includes(item.grade_level) &&
        item.subjects.some((candidate) => candidate.subject === subject),
    );
    const target =
      offered.find(
        (item) => item.grade_level === meta.grade_level && item.section === current?.section,
      ) ??
      offered.find((item) => item.grade_level === meta.grade_level) ??
      offered[0];
    if (!target) return;
    await goTo(target.id, subject, nextSemester);
  };

  return (
    <>
      <AcademicContextBar
        years={years}
        yearId={meta.year_id}
        semesterNumber={meta.semester_number}
        onYearChange={(next) => void switchYear(next)}
        onSemesterChange={(next) => void goTo(Number(classId), subject, next)}
        labels={academicContextLabels(t, lockedLabel)}
      />

      <div
        className={`flex flex-col gap-3 rounded-xl border border-border bg-card shadow-card lg:flex-row lg:items-center ${compact ? "p-2" : "p-3"}`}
      >
        <Segmented
          ariaLabel={t("classes.gradeLevel")}
          options={grades.map((item) => ({ value: item, label: gradeTabLabel(t, item) }))}
          value={meta.grade_level}
          onChange={(next) => goToBoard(next, subject)}
          size="sm"
          className="max-w-full"
        />
        {subjects.length > 1 ? (
          <Segmented
            ariaLabel={t("grid.subject")}
            options={subjects.map((item) => ({ value: item, label: t(`subjects.${item}`) }))}
            value={subject}
            onChange={(next) => goToBoard(meta.grade_level, next)}
            size="sm"
            className="max-w-full"
          />
        ) : null}
        <div className="flex min-w-0 flex-1 flex-wrap items-end gap-1 lg:justify-end">
          {gradeTabs.map((schoolClass) => (
            <button
              key={schoolClass.id}
              type="button"
              aria-current={schoolClass.id === Number(classId) ? "page" : undefined}
              className={[
                "min-w-0 flex-1 basis-16 rounded-lg px-2 py-2 text-xs font-semibold outline-none transition-colors sm:text-sm",
                schoolClass.id === Number(classId)
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              ].join(" ")}
              onPointerEnter={() => void prefetchBoard(schoolClass.id)}
              onFocus={() => void prefetchBoard(schoolClass.id)}
              onClick={() => void goTo(schoolClass.id, subject, meta.semester_number)}
            >
              {schoolClass.name}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
