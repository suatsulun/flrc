import type { ClassCatalogOut } from "@flrc/api-client";

/** Class reports cover middle-school English: grades 5 to 8 (ADR-074). */
export const REPORT_GRADES: readonly number[] = [5, 6, 7, 8];

/** Middle-school English classes in a catalog, optionally only the teacher's own. */
export function reportClasses(catalog: ClassCatalogOut[], { mine }: { mine: boolean }) {
  return catalog.filter(
    (schoolClass) =>
      REPORT_GRADES.includes(schoolClass.grade_level) &&
      schoolClass.subjects.some(
        (entry) => entry.subject === "english" && (!mine || entry.my_roles.length > 0),
      ),
  );
}
