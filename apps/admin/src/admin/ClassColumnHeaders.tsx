import { useDragPageAutoScroll } from "@flrc/ui/hooks/use-drag-page-auto-scroll";
import type { ColumnCreate } from "@flrc/api-client";
import { reorderColumnsMutation, updateColumnMutation, type ColumnOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeftIcon, ArrowRightIcon, GripVerticalIcon } from "lucide-react";
import { useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
type Subject = ColumnCreate["subject"];
type Role = ColumnCreate["owner_role"];

export function ClassColumnHeaders({
  columns,
  subject,
  semesterId,
  writable,
  onChanged,
}: {
  columns: ColumnOut[];
  subject: Subject;
  semesterId?: number;
  writable: boolean;
  onChanged: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const [draggedColumnId, setDraggedColumnId] = useState<number>();
  useDragPageAutoScroll(Boolean(draggedColumnId));
  const [columnDropTarget, setColumnDropTarget] = useState<number>();
  const visibleColumns = columns.filter((column) => column.is_active);
  const ownerRoles = subject === "english" ? (["main", "skills"] as const) : [subject];
  const updateColumn = useMutation({
    ...updateColumnMutation(),
    onSuccess: async () => {
      toast.success(t("feedback.saved"));
      await onChanged();
    },
  });
  const [reorderingColumnId, setReorderingColumnId] = useState<number>();
  const reorder = useMutation({
    ...reorderColumnsMutation(),
    onSuccess: async () => {
      toast.success(t("feedback.saved"));
      await onChanged();
    },
    onError: () => {
      void onChanged();
    },
    onSettled: () => setReorderingColumnId(undefined),
  });

  function moveColumn(from: number, to: number) {
    if (!semesterId || reorder.isPending || !writable) return;
    if (from < 0 || to < 0 || from === to || to >= visibleColumns.length) return;
    const ordered = visibleColumns.map((column) => column.id);
    const [columnId] = ordered.splice(from, 1);
    ordered.splice(to, 0, columnId);
    setReorderingColumnId(columnId);
    reorder.mutate({
      query: { semester_id: semesterId },
      body: { ordered_ids: [...ordered, ...columns.filter((c) => !c.is_active).map((c) => c.id)] },
    });
  }

  function dropColumn(event: DragEvent, targetId: number) {
    const sourceId =
      Number(event.dataTransfer.getData("application/x-flrc-column-id")) || draggedColumnId;
    if (!sourceId || !writable || reorder.isPending) return;
    event.preventDefault();
    moveColumn(
      visibleColumns.findIndex((column) => column.id === sourceId),
      visibleColumns.findIndex((column) => column.id === targetId),
    );
    setDraggedColumnId(undefined);
    setColumnDropTarget(undefined);
  }

  return (
    <>
      {visibleColumns.map((column, index) => (
        <th
          key={column.id}
          data-testid="class-column-header"
          data-column-id={column.id}
          className={`sticky top-0 z-30 border-b border-l border-border p-1.5 text-center align-top ${columnDropTarget === column.id ? "bg-accent ring-2 ring-inset ring-primary" : "bg-muted"}`}
          onDragOver={(event) => {
            if (
              event.dataTransfer.types.includes("application/x-flrc-column-id") &&
              writable &&
              !reorder.isPending
            ) {
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              setColumnDropTarget(column.id);
            }
          }}
          onDragLeave={() => setColumnDropTarget(undefined)}
          onDrop={(event) => dropColumn(event, column.id)}
        >
          {writable ? (
            <button
              type="button"
              draggable={!reorder.isPending}
              disabled={reorder.isPending}
              className="mb-1 flex w-full cursor-grab justify-center rounded p-1 text-muted-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
              aria-label={t("classWorkspace.dragColumn", {
                name: column.labels.tr,
              })}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("application/x-flrc-column-id", String(column.id));
                setDraggedColumnId(column.id);
              }}
              onDragEnd={() => {
                setDraggedColumnId(undefined);
                setColumnDropTarget(undefined);
              }}
            >
              <GripVerticalIcon className="size-3" />
            </button>
          ) : null}
          <span
            className="block min-w-0 font-semibold break-words [hyphens:auto]"
            title={column.labels.tr}
          >
            {column.labels.tr}
          </span>
          <div className="mt-1 grid grid-cols-2 gap-0.5">
            {writable
              ? ([-1, 1] as const).map((offset) => (
                  <Button
                    key={offset}
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    className="h-5 w-full min-w-0 rounded"
                    disabled={
                      index + offset < 0 ||
                      index + offset >= visibleColumns.length ||
                      Boolean(reorderingColumnId)
                    }
                    pending={reorderingColumnId === column.id && reorder.isPending}
                    pendingLabel={t("feedback.saving")}
                    aria-label={t(
                      offset === -1
                        ? "classWorkspace.moveColumnLeft"
                        : "classWorkspace.moveColumnRight",
                    )}
                    onClick={() => moveColumn(index, index + offset)}
                  >
                    {offset === -1 ? (
                      <ArrowLeftIcon className="size-3" />
                    ) : (
                      <ArrowRightIcon className="size-3" />
                    )}
                  </Button>
                ))
              : null}
          </div>
          <div className="mt-1 min-w-0">
            {writable ? (
              <NativeSelect
                className="h-7 w-full min-w-0 px-1.5 pr-5 text-xs"
                aria-label={t("classWorkspace.columnOwner")}
                title={t(`roles.${column.owner_role}`)}
                value={column.owner_role}
                onChange={(event) =>
                  semesterId &&
                  updateColumn.mutate({
                    path: { column_id: column.id },
                    query: { semester_id: semesterId },
                    body: { owner_role: event.target.value as Role },
                  })
                }
              >
                {ownerRoles.map((role) => (
                  <option key={role} value={role}>
                    {t(`roles.${role}`)}
                  </option>
                ))}
              </NativeSelect>
            ) : (
              <span title={t(`roles.${column.owner_role}`)}>{t(`roles.${column.owner_role}`)}</span>
            )}
          </div>
        </th>
      ))}
    </>
  );
}
