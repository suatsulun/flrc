import { useEffect, useMemo, useRef, useState } from "react";
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { GRADES, classLabel, gradeLabel } from "@flrc/i18n";
import { useStore } from "zustand";
import {
  ArrowDownIcon,
  CheckCircle2Icon,
  PlusIcon,
  SearchIcon,
  Undo2Icon,
  XIcon,
} from "lucide-react";
import { toast } from "sonner";
import {
  commitImportMutation,
  dryRunImport,
  type DryRunImportData,
  type PreviewRow,
} from "@flrc/api-client";
import { Badge } from "@flrc/ui/components/badge";
import { Button } from "@flrc/ui/components/button";
import { Card, CardBody, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";
import { Stat } from "@flrc/ui/components/stat";
import { useDragPageAutoScroll } from "@flrc/ui/hooks/use-drag-page-auto-scroll";
import { createImportDraft } from "./draft";
import { ImportRoster } from "./ImportRoster";
import { ImportAddStudent } from "./ImportAddStudent";

type Filters = {
  q: string;
  grade: string;
  schoolClass: string;
  language: NonNullable<DryRunImportData["query"]["language"]> | "";
  action: NonNullable<DryRunImportData["query"]["action"]> | "";
};
const EMPTY_FILTERS: Filters = { q: "", grade: "", schoolClass: "", language: "", action: "" };
const ACTIONS = [
  "new_student",
  "placed",
  "rename",
  "move",
  "class_changed",
  "language_change",
  "unchanged",
  "manual_added",
  "language_edited",
] as const;

export function ImportReview({
  reviewId,
  file,
  yearId,
  yearLabel,
  onCommittingChange,
}: {
  reviewId: string;
  file: File;
  yearId: number;
  yearLabel: string;
  onCommittingChange: (value: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [store] = useState(createImportDraft);
  const draft = useStore(store);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [search, setSearch] = useState("");
  const [trayGrade, setTrayGrade] = useState<number>();
  const [dragged, setDragged] = useState<PreviewRow>();
  const [dropTarget, setDropTarget] = useState<string>();
  const [announcement, setAnnouncement] = useState("");
  const [addingStudent, setAddingStudent] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);
  const movesJson = useMemo(
    () =>
      JSON.stringify(Object.values(draft.moves).sort((a, b) => a.school_number - b.school_number)),
    [draft.moves],
  );
  const moveCount = Object.keys(draft.moves).length;
  const editCount =
    moveCount +
    Object.keys(draft.additions).length +
    draft.removed.length +
    Object.keys(draft.languages).length;
  const editsJson = useMemo(
    () =>
      JSON.stringify({
        additions: Object.values(draft.additions).sort((a, b) => a.school_number - b.school_number),
        removed_school_numbers: [...draft.removed].sort((a, b) => a - b),
        language_changes: Object.values(draft.languages).sort(
          (a, b) => a.school_number - b.school_number,
        ),
      }),
    [draft.additions, draft.removed, draft.languages],
  );

  const commit = useMutation({
    ...commitImportMutation(),
    onMutate: () => onCommittingChange(true),
    onSuccess: async () => {
      toast.success(t("import.committed"));
      await queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== "import-review",
      });
    },
    onSettled: () => onCommittingChange(false),
  });
  const review = useInfiniteQuery({
    queryKey: ["import-review", reviewId, yearId, movesJson, editsJson, filters],
    queryFn: async ({ pageParam, signal }) => {
      const [classGrade, ...sectionParts] = filters.schoolClass.split("/");
      const section = sectionParts.join("/");
      const response = await dryRunImport({
        query: {
          year_id: yearId,
          offset: pageParam,
          limit: 100,
          q: filters.q,
          grade_level: filters.schoolClass
            ? Number(classGrade)
            : filters.grade
              ? Number(filters.grade)
              : undefined,
          section: section || undefined,
          language: filters.language || undefined,
          action: filters.action || undefined,
        },
        body: { file, class_moves: movesJson, roster_edits: editsJson },
        signal,
        throwOnError: true,
      });
      return response.data;
    },
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    placeholderData: keepPreviousData,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
    enabled: !commit.isSuccess,
  });
  const preview = review.data?.pages[0];
  const destinationGrades = [...new Set(preview?.classes.map((item) => item.grade_level) ?? [])];
  const selectedTrayGrade =
    trayGrade !== undefined && destinationGrades.includes(trayGrade)
      ? trayGrade
      : destinationGrades[0];
  const rows = review.data?.pages.flatMap((page) => page.rows) ?? [];
  const refreshing = review.isFetching && !review.isFetchingNextPage;
  const busy = commit.isPending || refreshing || review.isPlaceholderData;
  const hasErrors = preview?.issues.some((issue) => issue.level === "error") ?? false;
  const canCommit =
    Boolean(preview?.total_rows) &&
    !addingStudent &&
    !hasErrors &&
    !review.isError &&
    !commit.isError &&
    !review.isFetching &&
    !busy;
  useDragPageAutoScroll(Boolean(dragged));

  useEffect(() => {
    const timer = window.setTimeout(
      () => setFilters((current) => (current.q === search ? current : { ...current, q: search })),
      250,
    );
    return () => window.clearTimeout(timer);
  }, [search]);

  const { fetchNextPage, hasNextPage, isFetching, isError } = review;
  useEffect(() => {
    const element = sentinel.current;
    if (!element || !hasNextPage || isFetching || isError || commit.isSuccess) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) void fetchNextPage();
      },
      { rootMargin: "300px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetching, isError, commit.isSuccess]);

  function moveStudent(item: PreviewRow, destination: string) {
    if (busy || !preview || destination === `${item.row.grade_level}/${item.row.section}`) return;
    const target = preview.classes.find((c) => `${c.grade_level}/${c.section}` === destination);
    if (!target) return;
    draft.move(
      {
        school_number: item.row.school_number,
        grade_level: target.grade_level,
        section: target.section,
      },
      { grade_level: item.original_grade_level, section: item.original_section },
    );
    setAnnouncement(
      t("import.moveStaged", {
        name: item.row.full_name,
        className: classLabel(target.grade_level, target.section),
      }),
    );
    setDragged(undefined);
    setDropTarget(undefined);
  }

  function clearFilters() {
    setSearch("");
    setFilters(EMPTY_FILTERS);
  }

  if (commit.isSuccess) {
    return (
      <Card>
        <CardBody className="space-y-4 p-5">
          <div className="flex items-center gap-3">
            <CheckCircle2Icon className="size-6 text-success" />
            <h2 className="text-lg font-semibold">{t("import.committed")}</h2>
          </div>
          <p>{t("import.resultSummary", { count: commit.data.total_rows, year: yearLabel })}</p>
          <p className="text-sm text-muted-foreground">{t("import.resultHint")}</p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Object.entries(commit.data.counts).map(([key, value]) => (
              <Stat key={key} value={value} label={t(`import.counts.${key}`)} />
            ))}
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <>
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>
      {preview ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Object.entries(preview.counts).map(([key, value]) => (
            <Stat key={key} value={value} label={t(`import.counts.${key}`)} />
          ))}
        </div>
      ) : null}
      {preview?.issues.length ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("import.issuesTitle")}</CardTitle>
            <Badge tone={hasErrors ? "danger" : "warning"}>{preview.issues.length}</Badge>
          </CardHeader>
          <CardBody>
            <ul className="divide-y divide-border">
              {preview.issues.map((issue, index) => (
                <li
                  key={`${issue.sheet}-${issue.cell}-${index}`}
                  className="flex items-start gap-3 px-4 py-2 text-sm"
                >
                  <Badge tone={issue.level === "error" ? "danger" : "warning"}>
                    {issue.sheet} {issue.cell}
                  </Badge>
                  <span>{issue.message}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid items-start gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside
          className="space-y-3 rounded-xl border border-border bg-card p-3 shadow-card lg:sticky lg:top-18"
          aria-label={t("import.classTray")}
        >
          <div>
            <h2 className="text-sm font-semibold">{t("import.classTray")}</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {t("import.classTrayHint")}
            </p>
          </div>
          <NativeSelect
            aria-label={t("import.destinationGrade")}
            className="w-full"
            value={selectedTrayGrade ?? ""}
            disabled={commit.isPending}
            onChange={(event) => {
              setTrayGrade(Number(event.target.value));
              setFilters({ ...filters, grade: event.target.value, schoolClass: "" });
            }}
          >
            {destinationGrades.map((grade) => (
              <option key={grade} value={grade}>
                {gradeLabel(t, grade)}
              </option>
            ))}
          </NativeSelect>
          <Button
            variant="outline"
            className="w-full"
            disabled={commit.isPending}
            onClick={() => setFilters({ ...filters, schoolClass: "", grade: "" })}
          >
            {t("import.allClasses")}
          </Button>
          <div className="grid grid-cols-3 gap-2">
            {preview?.classes
              .filter((item) => item.grade_level === selectedTrayGrade)
              .map((item) => {
                const label = `${item.grade_level}/${item.section}`;
                const name = classLabel(item.grade_level, item.section);
                const selected = filters.schoolClass === label;
                return (
                  <button
                    key={label}
                    type="button"
                    data-testid="import-class-target"
                    data-class={label}
                    aria-label={t("import.viewClass", { className: name, count: item.count })}
                    aria-pressed={selected}
                    disabled={commit.isPending}
                    className={`rounded-lg border px-2 py-2 text-center outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring ${dropTarget === label ? "border-primary bg-accent ring-2 ring-primary" : selected ? "border-primary bg-accent text-accent-foreground" : "border-border bg-muted/30 hover:border-primary"}`}
                    onClick={() =>
                      setFilters({
                        ...filters,
                        schoolClass: label,
                        grade: String(item.grade_level),
                      })
                    }
                    onDragOver={(event) => {
                      if (dragged && !busy) {
                        event.preventDefault();
                        event.dataTransfer.dropEffect = "move";
                        setDropTarget(label);
                      }
                    }}
                    onDragLeave={() => setDropTarget(undefined)}
                    onDrop={(event) => {
                      event.preventDefault();
                      if (dragged) moveStudent(dragged, label);
                    }}
                  >
                    <span className="block text-sm font-semibold">{name}</span>
                    <span className="tabular text-xs text-muted-foreground">{item.count}</span>
                  </button>
                );
              })}
          </div>
          {moveCount ? (
            <p className="text-xs text-muted-foreground">
              {t("import.pendingMoves", { count: moveCount })}
            </p>
          ) : null}
          {editCount ? (
            <p className="text-xs text-muted-foreground">
              {t("import.pendingEdits", { count: editCount })}
            </p>
          ) : null}
          {draft.removed.length ? (
            <p className="text-xs text-muted-foreground">
              {t("import.excludedStudents", { count: draft.removed.length })}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!draft.history.length || busy}
              onClick={() => {
                draft.undo();
                setAnnouncement(t("import.moveUndone"));
              }}
            >
              <Undo2Icon />
              {t("import.undoMove")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={!editCount || busy}
              onClick={() => {
                draft.reset();
                setAnnouncement(t("import.movesReset"));
              }}
            >
              {t("import.resetMoves")}
            </Button>
          </div>
        </aside>

        <Card className="min-w-0" aria-busy={review.isFetching}>
          <CardHeader>
            <CardTitle>{t("import.rowsTitle")}</CardTitle>
            <Badge tone="neutral">{preview?.total_rows ?? "…"}</Badge>
            <Button
              className="ml-auto"
              size="sm"
              variant="outline"
              disabled={busy || !preview}
              onClick={() => setAddingStudent((v) => !v)}
            >
              <PlusIcon />
              {t("import.addStudent")}
            </Button>
          </CardHeader>
          <CardBody>
            <div className="space-y-3 border-b border-border p-3">
              {addingStudent && preview ? (
                <ImportAddStudent
                  classes={preview.classes}
                  initialClass={
                    filters.schoolClass ||
                    (() => {
                      const c =
                        preview.classes.find((c) => c.grade_level === selectedTrayGrade) ??
                        preview.classes[0];
                      return c ? `${c.grade_level}/${c.section}` : "";
                    })()
                  }
                  busy={busy}
                  onClose={() => setAddingStudent(false)}
                  onAdd={(student) => {
                    draft.add(student);
                    setAddingStudent(false);
                    setSearch("");
                    setFilters({
                      ...EMPTY_FILTERS,
                      grade: String(student.grade_level),
                      schoolClass: `${student.grade_level}/${student.section}`,
                    });
                    setTrayGrade(student.grade_level);
                    setAnnouncement(t("import.studentStaged", { name: student.full_name }));
                  }}
                />
              ) : null}
              <div className="relative">
                <SearchIcon className="pointer-events-none absolute top-3 left-3 size-4 text-muted-foreground" />
                <Input
                  className="pl-9"
                  aria-label={t("import.search")}
                  placeholder={t("import.search")}
                  value={search}
                  disabled={commit.isPending}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
                <NativeSelect
                  aria-label={t("import.filterGrade")}
                  disabled={commit.isPending}
                  value={filters.grade}
                  onChange={(event) => {
                    setFilters({ ...filters, grade: event.target.value, schoolClass: "" });
                    if (event.target.value) setTrayGrade(Number(event.target.value));
                  }}
                >
                  <option value="">{t("import.allGrades")}</option>
                  {GRADES.map((grade) => (
                    <option key={grade} value={grade}>
                      {gradeLabel(t, grade)}
                    </option>
                  ))}
                </NativeSelect>
                <NativeSelect
                  aria-label={t("import.filterClass")}
                  disabled={commit.isPending}
                  value={filters.schoolClass}
                  onChange={(event) => setFilters({ ...filters, schoolClass: event.target.value })}
                >
                  <option value="">{t("import.allClasses")}</option>
                  {preview?.classes
                    .filter((c) => !filters.grade || c.grade_level === Number(filters.grade))
                    .map((c) => (
                      <option
                        key={`${c.grade_level}/${c.section}`}
                        value={`${c.grade_level}/${c.section}`}
                      >
                        {classLabel(c.grade_level, c.section)} ({c.count})
                      </option>
                    ))}
                </NativeSelect>
                <NativeSelect
                  aria-label={t("import.filterLanguage")}
                  disabled={commit.isPending}
                  value={filters.language}
                  onChange={(event) =>
                    setFilters({ ...filters, language: event.target.value as Filters["language"] })
                  }
                >
                  <option value="">{t("import.allLanguages")}</option>
                  <option value="german">{t("subjects.german")}</option>
                  <option value="french">{t("subjects.french")}</option>
                  <option value="none">{t("import.noLanguage")}</option>
                </NativeSelect>
                <NativeSelect
                  aria-label={t("import.filterAction")}
                  disabled={commit.isPending}
                  value={filters.action}
                  onChange={(event) =>
                    setFilters({ ...filters, action: event.target.value as Filters["action"] })
                  }
                >
                  <option value="">{t("import.allActions")}</option>
                  {ACTIONS.map((action) => (
                    <option key={action} value={action}>
                      {t(`import.rowActions.${action}`)}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span role="status">
                  {refreshing
                    ? t("import.previewing")
                    : t("import.showingRows", {
                        shown: rows.length,
                        filtered: preview?.filtered_rows ?? 0,
                        total: preview?.total_rows ?? 0,
                      })}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={commit.isPending}
                  onClick={clearFilters}
                >
                  <XIcon />
                  {t("import.clearFilters")}
                </Button>
              </div>
            </div>
            {review.isError ? (
              <div role="alert" className="space-y-2 p-4 text-sm text-destructive">
                <p>{t("import.previewFailed")}</p>
                <Button
                  variant="outline"
                  onClick={() =>
                    review.isFetchNextPageError
                      ? void review.fetchNextPage()
                      : void review.refetch()
                  }
                >
                  {t("import.retry")}
                </Button>
              </div>
            ) : null}
            <ImportRoster
              rows={rows}
              classes={preview?.classes ?? []}
              busy={busy}
              loading={review.isPending}
              refreshing={refreshing}
              onMove={moveStudent}
              onRemove={(item) => {
                draft.remove(item.row.school_number);
                setAnnouncement(t("import.studentExcluded", { name: item.row.full_name }));
              }}
              onLanguage={(item, language) =>
                draft.setLanguage({ school_number: item.row.school_number, language })
              }
              onDrag={setDragged}
              onDragEnd={() => {
                setDragged(undefined);
                setDropTarget(undefined);
              }}
            />
            <div
              ref={sentinel}
              data-testid="import-scroll-sentinel"
              className="flex min-h-20 items-center justify-center p-4 text-sm text-muted-foreground"
            >
              {review.hasNextPage ? (
                <Button
                  variant="ghost"
                  pending={review.isFetchingNextPage}
                  pendingLabel={t("import.loadingMore")}
                  disabled={busy}
                  onClick={() => void review.fetchNextPage()}
                >
                  <ArrowDownIcon />
                  {t("import.scrollForMore")}
                </Button>
              ) : preview ? (
                t("import.endOfResults", { count: preview.filtered_rows })
              ) : null}
            </div>
          </CardBody>
        </Card>
      </div>
      <div className="sticky bottom-4 z-30 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card/95 px-4 py-3 shadow-raised backdrop-blur">
        <div className="min-w-0 flex-1 text-sm">
          <p className={hasErrors ? "text-destructive" : "font-medium"}>
            {hasErrors
              ? t("import.blocked")
              : t("import.commitScope", { count: preview?.total_rows ?? 0, year: yearLabel })}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t("import.commitHint", { count: editCount })}
          </p>
          {commit.isError ? (
            <div role="alert" className="mt-1 space-y-2 text-destructive">
              <p>{t("import.commitFailed")}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  commit.reset();
                  void review.refetch();
                }}
              >
                {t("import.refreshReview")}
              </Button>
            </div>
          ) : null}
        </div>
        <Button
          disabled={!canCommit}
          pending={commit.isPending}
          pendingLabel={t("import.committing")}
          onClick={() =>
            preview &&
            commit.mutate({
              query: {
                year_id: yearId,
                expected_sha256: preview.sha256,
                expected_review_sha256: preview.review_sha256,
              },
              body: { file, class_moves: movesJson, roster_edits: editsJson },
            })
          }
        >
          {t("import.commit")}
        </Button>
      </div>
    </>
  );
}
