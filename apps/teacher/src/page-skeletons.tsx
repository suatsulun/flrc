import { GRADES } from "@flrc/i18n";
import { Card } from "@flrc/ui/components/card";
import {
  Skeleton,
  SkeletonFields,
  SkeletonGrid,
  SkeletonList,
  SkeletonStudentCards,
  SkeletonTable,
  SkeletonTabs,
  SkeletonToolbar,
} from "@flrc/ui/components/skeleton";
import { REPORT_GRADES } from "./class-report/scope";

/*
 * Each teacher page's loading shape, built from the shared skeleton blocks. A page shows its
 * skeleton until its first data arrives, and the router shows the same skeleton while the
 * page's code loads (route-pending.tsx). Every block is aria-hidden; the shell's
 * PageActivity announces the load once.
 */

/** The grade and subject pickers' card with the class tabs of the grade. */
export function ClassTabsSkeleton() {
  return (
    <div aria-hidden className="flex min-w-0 flex-1 flex-wrap items-end gap-1 lg:justify-end">
      {Array.from({ length: 5 }, (_, index) => (
        <Skeleton key={index} className="h-9 min-w-0 flex-1 basis-16 max-md:h-10" />
      ))}
    </div>
  );
}

/** `BoardSwitcher`: the year bar above the grade, subject and class pickers. */
function BoardSwitcherSkeleton({ grades, subjects }: { grades: number; subjects: boolean }) {
  return (
    <>
      <SkeletonToolbar />
      <div
        aria-hidden
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-2 shadow-card lg:flex-row lg:items-center"
      >
        <SkeletonTabs count={grades} size="sm" />
        {subjects ? <SkeletonTabs count={3} size="sm" /> : null}
        <ClassTabsSkeleton />
      </div>
    </>
  );
}

/** "Sınıf raporu | Karne önizleme", above both report views. */
function ReportModeSwitchSkeleton() {
  return <SkeletonTabs count={2} />;
}

/**
 * A board page's heading: an optional overline, the class and subject, a summary line and the
 * page's actions, led on phones by "Kartlar | Tablo" where the page has that switch.
 */
function BoardHeadingSkeleton({
  actions,
  overline,
  viewSwitch = false,
}: {
  actions: number;
  overline: boolean;
  viewSwitch?: boolean;
}) {
  return (
    <div aria-hidden className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0 space-y-2">
        {overline ? <Skeleton className="h-3 w-24 rounded-md" /> : null}
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-64 max-w-full rounded-md" />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {viewSwitch ? <SkeletonTabs count={2} className="md:hidden" /> : null}
        {Array.from({ length: actions }, (_, index) => (
          <Skeleton key={index} className="h-8 w-28 max-md:h-10" />
        ))}
      </div>
    </div>
  );
}

/** The grade grid: switcher, heading, the grid and its save bar. */
export function GridPageSkeleton() {
  return (
    <div className="space-y-2">
      <BoardSwitcherSkeleton grades={GRADES.length} subjects />
      <BoardHeadingSkeleton actions={2} overline={false} />
      <SkeletonGrid />
      <div
        aria-hidden
        className="flex items-center gap-4 rounded-xl border border-border bg-card px-4 py-2.5 shadow-raised"
      >
        <Skeleton className="h-4 w-32 rounded-md" />
        <Skeleton className="ml-auto h-9 w-28" />
      </div>
    </div>
  );
}

/**
 * Sınıf raporu: the mode switch, the middle-school English class pickers and the sheet, which
 * phones show as one card per student.
 */
export function ClassReportSkeleton() {
  return (
    <div className="space-y-4">
      <ReportModeSwitchSkeleton />
      <BoardSwitcherSkeleton grades={REPORT_GRADES.length} subjects={false} />
      <BoardHeadingSkeleton actions={4} overline viewSwitch />
      <Card aria-hidden className="hidden overflow-hidden md:block">
        <SkeletonTable columns={8} rows={10} />
      </Card>
      <SkeletonStudentCards cards={4} columns={6} className="md:hidden" />
    </div>
  );
}

/** Karne önizleme: the mode switch, the class and semester pickers, the pupils and the card. */
export function CardPreviewSkeleton() {
  return (
    <div className="space-y-4">
      <ReportModeSwitchSkeleton />
      <div aria-hidden className="min-w-0 space-y-2">
        <Skeleton className="h-3 w-28 rounded-md" />
        <Skeleton className="h-7 w-56 max-w-2/3" />
        <Skeleton className="h-4 w-48 rounded-md" />
        <Skeleton className="h-4 w-full max-w-3xl rounded-md" />
      </div>
      <div aria-hidden className="flex flex-wrap items-end gap-3">
        <SkeletonFields count={1} className="min-w-56" />
        <SkeletonTabs count={2} />
      </div>
      <div aria-hidden className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <Card className="p-1">
          <SkeletonList rows={8} className="divide-y-0" />
        </Card>
        <Skeleton className="h-[min(78vh,52rem)] rounded-xl" />
      </div>
    </div>
  );
}

/** Sign-in: the school's mark above the one-button card. */
export function LoginSkeleton() {
  return (
    <main aria-hidden className="grid min-h-svh place-items-center px-4 py-10">
      <div className="flex w-full max-w-sm flex-col items-center">
        <Skeleton className="h-28 w-40 rounded-2xl" />
        <Skeleton className="mt-5 h-7 w-56" />
        <Card className="mt-8 w-full space-y-4 p-6">
          <Skeleton className="mx-auto h-4 w-4/5 rounded-md" />
          <Skeleton className="h-10 w-full" />
        </Card>
      </div>
    </main>
  );
}
