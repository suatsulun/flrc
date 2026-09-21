import type { TFunction } from "i18next";

export function academicContextLabels(t: TFunction, locked: string) {
  return {
    year: t("classWorkspace.year"),
    previousYear: t("classWorkspace.previousYear"),
    nextYear: t("classWorkspace.nextYear"),
    semester: t("classWorkspace.semester"),
    semesterShort: (number: number) => t("classWorkspace.semesterShort", { number }),
    active: t("lifecycle.active"),
    setup: t("lifecycle.setup"),
    archived: t("lifecycle.archived"),
    locked,
  };
}

export function appShellLabels(t: TFunction) {
  return {
    menu: t("shell.menu"),
    closeMenu: t("shell.closeMenu"),
    mainNavigation: t("shell.mainNavigation"),
    skipToContent: t("shell.skipToContent"),
    logout: t("logout"),
    collapseSidebar: t("shell.collapseSidebar"),
    expandSidebar: t("shell.expandSidebar"),
    collapseHeader: t("shell.collapseHeader"),
    expandHeader: t("shell.expandHeader"),
    theme: {
      light: t("shell.theme.light"),
      dark: t("shell.theme.dark"),
      system: t("shell.theme.system"),
    },
  };
}

/** Hazırlık, the primary school's preparatory year, is stored as grade 0 (ADR-065). */
export const PREP_GRADE = 0;
export const GRADES: readonly number[] = [PREP_GRADE, 1, 2, 3, 4, 5, 6, 7, 8];

/** `Bulut` for a Hazırlık class, `5/A` for every other grade. */
export function classLabel(gradeLevel: number, section: string) {
  return gradeLevel === PREP_GRADE ? section : `${gradeLevel}/${section}`;
}

/** A grade option in a select: `Hazırlık` or `5. sınıf`. */
export function gradeLabel(t: TFunction, grade: number) {
  return grade === PREP_GRADE ? t("classes.prep") : t("classes.grade", { grade });
}

/** The compact form for segmented controls: `Hazırlık` or `5`. */
export function gradeTabLabel(t: TFunction, grade: number) {
  return grade === PREP_GRADE ? t("classes.prep") : String(grade);
}
