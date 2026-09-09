import {
  listAssignmentMatrixOptions,
  listManagedUsersOptions,
  replaceAssignmentMatrixMutation,
} from "@flrc/api-client";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useRefreshQueries } from "./use-refresh-queries";
const ROLES = ["main", "skills", "german", "french"] as const;

export function ClassTeachers({
  yearId,
  classId,
  grade,
  writable,
}: {
  yearId: number;
  classId: number;
  grade: number;
  writable: boolean;
}) {
  const { t } = useTranslation();
  const invalidate = useRefreshQueries();
  const { data: matrix = [] } = useQuery(
    listAssignmentMatrixOptions({ path: { year_id: yearId } }),
  );
  const { data: users = [] } = useQuery(listManagedUsersOptions({ query: { active: true } }));
  const assign = useMutation({
    ...replaceAssignmentMatrixMutation(),
    onSuccess: () => {
      toast.success(t("feedback.saved"));
      void invalidate("listAssignmentMatrix", "getAssignments", "getGrid");
    },
  });

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <strong className="mr-2 text-sm">{t("classWorkspace.teachers")}</strong>
        {ROLES.map((role) => {
          const slot = matrix.find((item) => item.class_id === classId && item.role === role);
          const expectedField = role === "main" || role === "skills" ? "english" : role;
          const expectedStage = grade <= 4 ? "primary" : "middle";
          return (
            <label key={role} className="flex items-center gap-1.5 text-xs">
              <span className="font-medium text-muted-foreground">{t(`roles.${role}`)}</span>
              <NativeSelect
                className="w-40"
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

      {assign.isError ? (
        <p role="alert" className="text-xs text-destructive">
          {t("assignmentBoard.saveFailed")}
        </p>
      ) : null}
    </>
  );
}
