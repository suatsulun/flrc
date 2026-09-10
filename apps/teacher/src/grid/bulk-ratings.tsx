import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { GridOut, GridRowOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@flrc/ui/components/dialog";
import { SCALE3_FACES } from "@flrc/ui/grid/cells";
import { useDirtyStore } from "./dirty-store";

export function BulkRatings({
  data,
  row,
  readOnly,
}: {
  data: GridOut;
  row?: GridRowOut;
  readOnly: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const count = data.columns.filter((column) => column.value_type === "scale3").length;
  if (!count || !data.rows.length || readOnly) return null;
  const showFaces = data.meta.subject === "english" && data.meta.grade_level <= 4;
  const title = row
    ? t("grid.bulkStudentTitle", { name: row.full_name })
    : t("grid.bulkClassTitle", { name: data.meta.class_name });
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="h-auto min-h-8 max-w-full py-1.5 whitespace-normal text-left"
        aria-label={title}
        data-testid={row ? `bulk-ratings-student-${row.student_id}` : "bulk-ratings-class"}
        onClick={() => setOpen(true)}
      >
        {row ? t("grid.bulkStudent") : t("grid.bulkClass")}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              {row
                ? t("grid.bulkStudentHint", { count })
                : t("grid.bulkClassHint", { students: data.rows.length, count })}{" "}
              {t("grid.bulkSaveHint")}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {([1, 2, 3] as const).map((level) => (
              <Button
                key={level}
                variant="outline"
                className="justify-start gap-3"
                data-testid={`bulk-rating-${level}`}
                onClick={() => {
                  useDirtyStore.getState().setRatings(data, level, row?.student_id);
                  setOpen(false);
                }}
              >
                <span className="tabular">{level}</span>
                {showFaces ? <span aria-hidden="true">{SCALE3_FACES[level]}</span> : null}
                {t(`grid.scaleLevels.${level}`)}
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
