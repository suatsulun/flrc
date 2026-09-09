import { createFileRoute, Navigate } from "@tanstack/react-router";

/**
 * Student creation and year-specific numbers now live inside class tables.
 *
 * Index-only: as a layout route this swallowed `/students/$id/history`, which
 * made the per-student history table unreachable.
 */
export const Route = createFileRoute("/_auth/students/")({
  component: () => <Navigate replace to="/classes" />,
});
