import { roleLabel } from "@flrc/i18n";
import {
  listAssignmentMatrixOptions,
  listManagedUsersOptions,
  replaceAssignmentMatrixMutation,
} from "@flrc/api-client";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { Skeleton } from "@flrc/ui/components/skeleton";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNotifyDone } from "./undo-toast";
import { useRefreshQueries } from "./use-refresh-queries";
const ROLES = ["main", "skills", "german", "french"] as const;

export function ClassTeachers({
  yearId,
  classId,
  className,
  grade,
  writable,
}: {
  yearId: number;
  classId: number;
  className: string;
  grade: number;
  writable: boolean;
}) {
  const { t } = useTranslation();
  const notifyDone = useNotifyDone();
  const invalidate = useRefreshQueries();
  const { data: matrix = [], isPending: matrixPending } = useQuery(
    listAssignmentMatrixOptions({ path: { year_id: yearId } }),
  );
  const { data: users = [], isPending: usersPending } = useQuery(
    listManagedUsersOptions({ query: { active: true } }),
  );
  const assign = useMutation({
    ...replaceAssignmentMatrixMutation(),
    // The toast names the class, role and teacher as they were when the change was sent.
    onMutate: ({ body }) => {
      const [change] = body.changes;
      return {
        className,
        role: roleLabel(t, change.role, grade),
        teacher: users.find((user) => user.id === change.user_id)?.full_name,
      };
    },
    onSuccess: (result, _variables, submitted) => {
      notifyDone(
        submitted.teacher
          ? t("classWorkspace.teacherAssigned", submitted)
          : t("classWorkspace.teacherUnassigned", submitted),
        result.action_id,
      );
      void invalidate("listAssignmentMatrix", "getAssignments", "getGrid");
    },
  });

  return (
    // Phones stack each role's name above a full-width select, so teacher names never clip.
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:flex md:flex-wrap md:items-center md:gap-2">
      <strong className="text-sm sm:col-span-2 md:mr-2">{t("classWorkspace.teachers")}</strong>
      {ROLES.map((role) => {
        const slot = matrix.find((item) => item.class_id === classId && item.role === role);
        const expectedField = role === "main" || role === "skills" ? "english" : role;
        const expectedStage = grade <= 4 ? "primary" : "middle";
        if (matrixPending || usersPending) {
          return (
            <span key={role} className="grid gap-1 text-xs md:flex md:items-center md:gap-1.5">
              <span className="font-medium text-muted-foreground">{roleLabel(t, role, grade)}</span>
              <Skeleton className="h-9 w-40 max-md:h-10 max-md:w-full" />
            </span>
          );
        }
        return (
          <label key={role} className="grid gap-1 text-xs md:flex md:items-center md:gap-1.5">
            <span className="font-medium text-muted-foreground">{roleLabel(t, role, grade)}</span>
            <NativeSelect
              className="w-40 max-md:w-full"
              value={slot?.user_id ?? ""}
              disabled={!writable || assign.isPending}
              onChange={(event) =>
                assign.mutate({
                  path: { year_id: yearId },
                  body: {
                    changes: [
                      {
                        class_id: classId,
                        role,
                        user_id: event.target.value ? Number(event.target.value) : null,
                      },
                    ],
                  },
                })
              }
            >
              <option value="">{t("assignments.unassigned")}</option>
              {users
                .filter(
                  (user) =>
                    user.teaching_field === expectedField &&
                    (expectedField !== "english" || user.teaching_stage === expectedStage),
                )
                .map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
            </NativeSelect>
          </label>
        );
      })}
    </div>
  );
}
