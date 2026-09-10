import type { GridColumnOut } from "@flrc/api-client";

export type AssessmentFilter = "all" | "notes" | `group:${string}`;

export function assessmentOptions(columns: GridColumnOut[]) {
  const counts = new Map<string, number>();
  for (const column of columns) {
    if (column.group && column.value_type !== "text")
      counts.set(column.group, (counts.get(column.group) ?? 0) + 1);
  }
  return [
    { id: "all" as AssessmentFilter, label: "", count: columns.length },
    ...[...counts].map(([label, count]) => ({
      id: `group:${label}` as AssessmentFilter,
      label,
      count,
    })),
    {
      id: "notes" as AssessmentFilter,
      label: "",
      count: columns.filter((column) => column.value_type === "text").length,
    },
  ];
}

export function filterAssessments(columns: GridColumnOut[], filter: AssessmentFilter) {
  if (filter === "all") return columns;
  if (filter === "notes") return columns.filter((column) => column.value_type === "text");
  return columns.filter(
    (column) => column.value_type !== "text" && column.group === filter.slice(6),
  );
}
