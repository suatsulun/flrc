import { getPreviewScopeOptions, type PreviewClassOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { Field } from "@flrc/ui/components/field";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { Segmented } from "@flrc/ui/components/segmented";
import { FileRequestError } from "@flrc/ui/lib/file-delivery";
import { cn } from "@flrc/ui/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  FileSearchIcon,
  LoaderCircleIcon,
  RotateCwIcon,
  UsersRoundIcon,
} from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { errorCode } from "../../class-report/api-error";
import { useCardPreviewPdf, type CardKind } from "../../class-report/card-preview-pdf";
import { usePdfErrorMessage } from "../../class-report/class-sheet-pdf";
import { ReportModeSwitch } from "../../class-report/report-mode-switch";
import { REPORT_GRADES } from "../../class-report/scope";
import { CardPreviewSkeleton } from "../../page-skeletons";

const CARD_KINDS: readonly CardKind[] = [
  "english_elementary",
  "english_middle",
  "german_karne",
  "french_karne",
];

function positiveId(value: unknown) {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : undefined;
}

export const Route = createFileRoute("/_auth/card-preview")({
  validateSearch: (search: Record<string, unknown>) => ({
    semesterId: positiveId(search.semesterId),
    classId: positiveId(search.classId),
    kind: CARD_KINDS.find((kind) => kind === search.kind),
    studentId: positiveId(search.studentId),
  }),
  component: CardPreviewPage,
});

/** Arrow keys page through students unless the teacher is typing or choosing in a field. */
function inFormField(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName))
  );
}

function entryKey(entry: Pick<PreviewClassOut, "class_id" | "kind">) {
  return `${entry.class_id}:${entry.kind}`;
}

function CardPreviewPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const { user } = Route.useRouteContext();
  const { t } = useTranslation();
  const pdfErrorMessage = usePdfErrorMessage();
  // Administrators and coordinators see every class of the year; teachers their own classes.
  const wholeSchool = user.is_admin || user.is_coordinator;

  const scopeQuery = useQuery(
    getPreviewScopeOptions({ query: { semester_id: search.semesterId } }),
  );

  const scope = scopeQuery.data;
  // The requested card, else another card of the requested class, else the first card.
  const entry =
    scope?.classes.find(
      (item) => item.class_id === search.classId && (!search.kind || item.kind === search.kind),
    ) ??
    scope?.classes.find((item) => item.class_id === search.classId) ??
    scope?.classes[0];
  const students = entry?.students ?? [];
  const foundIndex = students.findIndex((student) => student.student_id === search.studentId);
  const index = foundIndex >= 0 ? foundIndex : 0;
  const student = students[index];
  const previousId = students[index - 1]?.student_id;
  const nextId = students[index + 1]?.student_id;

  const preview = useCardPreviewPdf(
    scope && entry && student
      ? { semesterId: scope.semester_id, studentId: student.student_id, kind: entry.kind }
      : null,
  );

  // Paging with the buttons or keys keeps the current student visible in a long list. Only the
  // list scrolls, so paging on a phone does not jump the page away from the card.
  const studentList = useRef<HTMLElement>(null);
  const currentStudentId = student?.student_id;
  useEffect(() => {
    const list = studentList.current;
    const item = list?.querySelector<HTMLElement>('[aria-current="true"]');
    if (currentStudentId === undefined || !list || !item) return;
    if (item.offsetTop < list.scrollTop) list.scrollTop = item.offsetTop;
    else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight;
  }, [currentStudentId]);

  useEffect(() => {
    if (!entry) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.defaultPrevented || inFormField(event.target)) return;
      const target =
        event.key === "ArrowLeft" ? previousId : event.key === "ArrowRight" ? nextId : undefined;
      if (target === undefined) return;
      event.preventDefault();
      void navigate({
        search: (previous) => ({
          ...previous,
          classId: entry.class_id,
          kind: entry.kind,
          studentId: target,
        }),
        replace: true,
      });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [entry, navigate, nextId, previousId]);

  const showStudent = (studentId: number) =>
    void navigate({
      search: (previous) => ({
        ...previous,
        classId: entry?.class_id,
        kind: entry?.kind,
        studentId,
      }),
      replace: true,
    });

  const cardLabel = (kind: CardKind) =>
    kind === "german_karne"
      ? t("cardPreview.cardGerman")
      : kind === "french_karne"
        ? t("cardPreview.cardFrench")
        : t("cardPreview.cardEnglish");

  // The class sheet opens on the class in view when it is a middle-school class, else on the
  // user's default class report.
  const modeSwitch = (
    <ReportModeSwitch
      mode="preview"
      onChange={() =>
        void (entry && REPORT_GRADES.includes(entry.grade_level)
          ? navigate({
              to: "/class-report/$classId",
              params: { classId: String(entry.class_id) },
              search: { semester: scope?.semester_number },
            })
          : navigate({ to: "/class-report" }))
      }
    />
  );

  const header = (
    <>
      {modeSwitch}
      <div className="min-w-0">
        <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          {t("cardPreview.title")}
        </p>
        <h1 className="font-heading text-xl font-semibold tracking-tight">
          {entry ? (
            <>
              {entry.class_name}
              <span className="text-muted-foreground"> · </span>
              {cardLabel(entry.kind)}
            </>
          ) : (
            t("cardPreview.title")
          )}
        </h1>
        {scope ? (
          <p className="mt-1 text-sm text-muted-foreground">
            {[
              scope.year_label,
              t("classReport.semester", { number: scope.semester_number }),
              ...(entry ? [t("classReport.students", { count: students.length })] : []),
            ].join(" · ")}
          </p>
        ) : null}
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {wholeSchool ? t("cardPreview.descriptionAll") : t("cardPreview.description")}
        </p>
      </div>
    </>
  );

  if (scopeQuery.isPending) return <CardPreviewSkeleton />;
  if (scopeQuery.isError || !scope) {
    const code = errorCode(scopeQuery.error);
    return (
      <div className="space-y-4">
        {header}
        {code === "semester_missing" ? (
          <EmptyState
            icon={<FileSearchIcon />}
            title={t("cardPreview.emptyTitle")}
            description={wholeSchool ? t("cardPreview.emptyAllBody") : t("cardPreview.emptyBody")}
          />
        ) : (
          <p className="text-sm text-destructive">{t("errors.load")}</p>
        )}
      </div>
    );
  }

  const failure =
    preview.status === "error"
      ? preview.error instanceof FileRequestError && preview.error.status === 403
        ? t("cardPreview.forbidden")
        : preview.error instanceof FileRequestError && preview.error.rateLimited
          ? pdfErrorMessage(preview.error)
          : t("cardPreview.failed")
      : null;

  return (
    <div className="space-y-4">
      {header}

      <div className="flex flex-wrap items-end gap-3">
        {scope.classes.length ? (
          <Field label={t("cardPreview.classLabel")} className="min-w-56">
            {(id) => (
              <NativeSelect
                id={id}
                value={entry ? entryKey(entry) : ""}
                onChange={(event) => {
                  const next = scope.classes.find((item) => entryKey(item) === event.target.value);
                  if (!next) return;
                  void navigate({
                    search: (previous) => ({
                      ...previous,
                      classId: next.class_id,
                      kind: next.kind,
                      studentId: undefined,
                    }),
                  });
                }}
              >
                {scope.classes.map((item) => (
                  <option key={entryKey(item)} value={entryKey(item)}>
                    {`${item.class_name} · ${cardLabel(item.kind)}`}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        ) : null}
        {scope.semesters.length > 1 ? (
          <Segmented<number>
            ariaLabel={t("cardPreview.semesterLabel")}
            value={scope.semester_id}
            onChange={(semesterId) =>
              void navigate({ search: (previous) => ({ ...previous, semesterId }) })
            }
            options={scope.semesters.map((term) => ({
              value: term.id,
              label: t("classReport.semester", { number: term.number }),
            }))}
          />
        ) : null}
      </div>

      {!entry ? (
        <EmptyState
          icon={<FileSearchIcon />}
          title={t("cardPreview.emptyTitle")}
          description={wholeSchool ? t("cardPreview.emptyAllBody") : t("cardPreview.emptyBody")}
        />
      ) : !student ? (
        <EmptyState
          icon={<UsersRoundIcon />}
          title={t("cardPreview.noStudentsTitle")}
          description={t("cardPreview.noStudentsBody")}
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <nav
            ref={studentList}
            aria-label={t("cardPreview.studentsLabel")}
            className="relative max-h-[70vh] overflow-y-auto rounded-xl border border-border bg-card p-1 lg:max-h-[min(78vh,52rem)]"
          >
            <ol className="space-y-0.5">
              {students.map((item, position) => (
                <li key={item.student_id}>
                  <button
                    type="button"
                    aria-current={position === index ? "true" : undefined}
                    onClick={() => showStudent(item.student_id)}
                    className={cn(
                      "flex w-full items-baseline gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors",
                      "focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                      position === index
                        ? "bg-primary/10 font-medium text-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <span className="tabular w-12 shrink-0 text-xs">
                      {item.school_number ?? "–"}
                    </span>
                    <span className="truncate">{item.full_name}</span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>

          <section className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={previousId === undefined}
                  onClick={() => previousId !== undefined && showStudent(previousId)}
                >
                  <ChevronLeftIcon />
                  {t("cardPreview.previous")}
                </Button>
                <span className="tabular min-w-14 text-center text-sm text-muted-foreground">
                  {t("cardPreview.position", { current: index + 1, total: students.length })}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={nextId === undefined}
                  onClick={() => nextId !== undefined && showStudent(nextId)}
                >
                  {t("cardPreview.next")}
                  <ChevronRightIcon />
                </Button>
              </div>
              <p className="min-w-0 truncate text-sm font-medium">
                {student.school_number ? `${student.school_number} · ` : ""}
                {student.full_name}
              </p>
            </div>

            <div className="relative h-[min(78vh,52rem)] overflow-hidden rounded-xl border border-border bg-muted/40">
              {preview.url && preview.status !== "error" ? (
                <iframe
                  key={preview.url}
                  src={`${preview.url}#toolbar=0&navpanes=0`}
                  title={t("cardPreview.frameTitle", { name: student.full_name })}
                  className={cn(
                    "size-full bg-card transition-opacity",
                    preview.status === "loading" && "opacity-40",
                  )}
                />
              ) : null}
              {preview.status === "loading" || preview.status === "idle" ? (
                <div
                  role="status"
                  className="absolute inset-0 grid place-items-center text-sm text-muted-foreground"
                >
                  <span className="inline-flex items-center gap-2 rounded-lg bg-card px-3 py-2 shadow-card">
                    <LoaderCircleIcon className="size-4 animate-spin" />
                    {t("cardPreview.loading")}
                  </span>
                </div>
              ) : null}
              {failure ? (
                <div
                  role="alert"
                  className="absolute inset-0 grid place-items-center px-6 text-center"
                >
                  <div className="max-w-sm space-y-3">
                    <p className="text-sm text-destructive">{failure}</p>
                    <Button variant="outline" size="sm" onClick={preview.retry}>
                      <RotateCwIcon />
                      {t("cardPreview.retry")}
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("cardPreview.keyboardHint")} {t("cardPreview.watermarkNote")}
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
