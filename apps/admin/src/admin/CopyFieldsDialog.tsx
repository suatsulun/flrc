import { GRADES, gradeLabel } from "@flrc/i18n";
import { copyColumnsMutation, listColumnsOptions, type ColumnOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@flrc/ui/components/dialog";
import { Field } from "@flrc/ui/components/field";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { SkeletonText } from "@flrc/ui/components/skeleton";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CopyIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNotifyDone } from "./undo-toast";

type Subject = "english" | "german" | "french";

const SUBJECT_LOCALE = { english: "en", german: "de", french: "fr" } as const;

// Mirrors backend academics/programme.py: which field types a grade and subject can hold, and
// where the printed card shows a field in Turkish.
function allowsType(grade: number, subject: Subject, valueType: string) {
  if (valueType === "text" && subject === "english" && grade >= 5) return false;
  return !(grade === 4 && subject !== "english") || valueType !== "score";
}

function printsTurkish(grade: number, subject: Subject, valueType: string) {
  return subject === "english" ? grade < 5 : valueType !== "score";
}

/**
 * Copy every field of one grade and subject to another of the same family in the open
 * semester (`POST /api/columns/copy`). The target must still be empty; the dialog shows how
 * many fields it would receive and why it cannot, and the API decides.
 */
export function CopyFieldsDialog({
  grade,
  subject,
  columns,
  onCopied,
}: {
  grade: number;
  subject: Subject;
  columns: ColumnOut[];
  onCopied: (target: { grade: number; subject: Subject }) => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const notifyDone = useNotifyDone();
  const [open, setOpen] = useState(false);
  // English copies to English only; German and French copy to each other.
  const subjects: Subject[] = subject === "english" ? ["english"] : ["german", "french"];
  const [targetGrade, setTargetGrade] = useState(grade);
  const [chosenSubject, setTargetSubject] = useState<Subject>(subject);
  const targetSubject = subjects.includes(chosenSubject) ? chosenSubject : subject;
  const sameScope = targetGrade === grade && targetSubject === subject;
  const { data: targetColumns, isPending: targetPending } = useQuery({
    ...listColumnsOptions({ query: { grade_level: targetGrade, subject: targetSubject } }),
    enabled: open && !sameScope,
  });
  const copies = columns.filter((column) =>
    allowsType(targetGrade, targetSubject, column.value_type),
  );
  const skipped = columns.length - copies.length;
  const locale = SUBJECT_LOCALE[targetSubject];
  const lacksName =
    targetSubject !== subject &&
    copies.some(
      (column) => !column.labels[locale] || (column.group_labels && !column.group_labels[locale]),
    );
  const lacksTurkish = copies.some(
    (column) =>
      printsTurkish(targetGrade, targetSubject, column.value_type) &&
      (!column.labels.tr || (column.group_labels && !column.group_labels.tr)),
  );
  const targetCount = targetColumns?.length ?? 0;
  const blocked =
    sameScope ||
    targetPending ||
    targetCount > 0 ||
    copies.length === 0 ||
    lacksName ||
    lacksTurkish;
  const copy = useMutation({
    ...copyColumnsMutation(),
    onSuccess: async (result, { body }) => {
      notifyDone(t("columns.copied", { count: result.copied }), result.action_id);
      setOpen(false);
      await onCopied({ grade: body.target_grade_level, subject: body.target_subject });
    },
  });
  const targetLabel = `${gradeLabel(t, targetGrade)} · ${t(`subjects.${targetSubject}`)}`;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (copy.isPending) return;
        setOpen(next);
        if (next) {
          setTargetGrade(grade);
          setTargetSubject(subject);
        }
      }}
    >
      <DialogTrigger render={<Button variant="outline" disabled={columns.length === 0} />}>
        <CopyIcon />
        {t("columns.copy")}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg" showCloseButton={!copy.isPending}>
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (blocked || copy.isPending) return;
            copy.mutate({
              body: {
                source_grade_level: grade,
                source_subject: subject,
                target_grade_level: targetGrade,
                target_subject: targetSubject,
              },
            });
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("columns.copyTitle")}</DialogTitle>
            <DialogDescription>
              {t("columns.copySource", {
                source: `${gradeLabel(t, grade)} · ${t(`subjects.${subject}`)}`,
                count: columns.length,
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("columns.copyTargetGrade")}>
              {(id) => (
                <NativeSelect
                  id={id}
                  value={targetGrade}
                  disabled={copy.isPending}
                  onChange={(event) => setTargetGrade(Number(event.target.value))}
                >
                  {GRADES.map((item) => (
                    <option key={item} value={item}>
                      {gradeLabel(t, item)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label={t("columns.copyTargetSubject")} hint={t("columns.copyFamily")}>
              {(id) => (
                <NativeSelect
                  id={id}
                  value={targetSubject}
                  disabled={copy.isPending}
                  onChange={(event) => setTargetSubject(event.target.value as Subject)}
                >
                  {subjects.map((item) => (
                    <option key={item} value={item}>
                      {t(`subjects.${item}`)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          </div>
          <div
            className="space-y-1.5 rounded-lg border border-border bg-muted/40 p-3 text-sm"
            role="status"
          >
            {sameScope ? (
              <p>{t("columns.copySame")}</p>
            ) : targetPending ? (
              <>
                <span className="sr-only">{t("loading")}</span>
                <SkeletonText lines={2} className="py-1" />
              </>
            ) : (
              <>
                <p className={targetCount > 0 ? "font-medium text-destructive" : undefined}>
                  {targetCount > 0
                    ? t("columns.copyTargetHas", { target: targetLabel, count: targetCount })
                    : t("columns.copyTargetEmpty", { target: targetLabel })}
                </p>
                {copies.length === 0 ? (
                  <p>{t("columns.copyNothing")}</p>
                ) : (
                  <p>{t("columns.copyPreview", { count: copies.length })}</p>
                )}
                {skipped > 0 ? (
                  <p className="text-muted-foreground">
                    {t("columns.copySkipped", { count: skipped })}
                  </p>
                ) : null}
                {lacksName ? (
                  <p className="text-destructive">
                    {t("columns.copyMissingName", { language: t(`subjects.${targetSubject}`) })}
                  </p>
                ) : null}
                {lacksTurkish ? (
                  <p className="text-destructive">{t("columns.copyMissingTurkish")}</p>
                ) : null}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={copy.isPending} onClick={() => setOpen(false)}>
              {t("forms.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={blocked}
              pending={copy.isPending}
              pendingLabel={t("feedback.saving")}
            >
              {t("columns.copySubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
