import type { ClassCatalogOut } from "@flrc/api-client";

/** Class reports cover middle-school English: grades 5 to 8 (ADR-074). */
export const REPORT_GRADES: readonly number[] = [5, 6, 7, 8];
const ENGLISH_ROLES = ["main", "skills"];

/**
 * Middle-school English classes in a catalog, optionally only the teacher's own. A teacher
 * owns a class through either English assignment, whether or not that role owns any of the
 * semester's fields, so the class-wide report uses the class's `assigned_roles`.
 */
export function reportClasses(catalog: ClassCatalogOut[], { mine }: { mine: boolean }) {
  return catalog.filter(
    (schoolClass) =>
      REPORT_GRADES.includes(schoolClass.grade_level) &&
      schoolClass.subjects.some((entry) => entry.subject === "english") &&
      (!mine || schoolClass.assigned_roles.some((role) => ENGLISH_ROLES.includes(role))),
  );
}

/** The class report a user opens by default: their own middle-school English class, else the first. */
export function defaultReportClass(catalog: ClassCatalogOut[]) {
  return reportClasses(catalog, { mine: true })[0] ?? reportClasses(catalog, { mine: false })[0];
}
