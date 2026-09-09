import { useState } from "react";
import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  saveGridMutation,
  type ConflictOut,
  type GridOut,
  type SaveRequest,
} from "@flrc/api-client";

import { dirtyKey, useDirtyStore } from "./dirty-store";
import { mergeSavedGrid } from "./merge-saved-grid";

type Arguments = { classId: number; subject: SaveRequest["subject"]; gridKey: QueryKey };

export function useSaveGrid({ classId, subject, gridKey }: Arguments) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [conflicts, setConflicts] = useState<ConflictOut[]>([]);
  const [savedFlash, setSavedFlash] = useState(false);

  const mutation = useMutation({
    ...saveGridMutation(),
    onMutate: ({ body }) => {
      const draft = useDirtyStore.getState();
      return {
        gridKey,
        generation: draft.generation,
        submitted: { cells: body.cells, draft: draft.cells },
      };
    },
    onSuccess: (response, _variables, context) => {
      const grid = queryClient.getQueryData<GridOut>(context.gridKey);
      const draft = useDirtyStore.getState();
      if (grid) {
        const merged = mergeSavedGrid(grid, draft.cells, context.submitted, response.applied);
        queryClient.setQueryData(context.gridKey, merged.grid);
        // A late response must not restore drafts after the user leaves/discards this grid.
        if (draft.generation === context.generation) {
          useDirtyStore.setState({ cells: merged.dirty });
        }
      }
      if (draft.generation !== context.generation) return;
      if (response.rejected.length) {
        toast.error(t("grid.rejected", { count: response.rejected.length }));
      }
      if (response.conflicts.length) setConflicts(response.conflicts);
      else {
        setConflicts([]);
        toast.success(t("grid.saved"));
        setSavedFlash(true);
        window.setTimeout(() => setSavedFlash(false), 2000);
      }
    },
  });

  const submit = (body: Omit<SaveRequest, "subject">) => {
    if (mutation.isPending || !body.cells.length) return;
    mutation.mutate({ path: { class_id: classId }, body: { ...body, subject } });
  };

  const saveAll = (confirmOutsideAssignment = false) =>
    submit({
      confirm_outside_assignment: confirmOutsideAssignment,
      cells: Object.values(useDirtyStore.getState().cells).map((cell) => ({
        student_id: cell.studentId,
        column_id: cell.columnId,
        value: cell.value,
        expected_version: cell.expectedVersion,
      })),
    });

  const acceptConflicts = () => {
    const dirty = useDirtyStore.getState().cells;
    submit({
      force: true,
      cells: conflicts.map((conflict) => {
        const cell = dirty[dirtyKey(conflict.student_id, conflict.column_id)];
        return {
          student_id: conflict.student_id,
          column_id: conflict.column_id,
          value: cell ? cell.value : conflict.your_value,
          expected_version: 0,
        };
      }),
    });
  };

  const cancelConflicts = () => {
    useDirtyStore
      .getState()
      .clearCells(conflicts.map((conflict) => dirtyKey(conflict.student_id, conflict.column_id)));
    setConflicts([]);
    void queryClient.invalidateQueries({ queryKey: gridKey });
  };

  return {
    saveAll,
    acceptConflicts,
    cancelConflicts,
    conflicts,
    savedFlash,
    isPending: mutation.isPending,
  };
}
