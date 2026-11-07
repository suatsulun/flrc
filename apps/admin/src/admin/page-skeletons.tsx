import { GRADES } from "@flrc/i18n";
import { Card, CardBody } from "@flrc/ui/components/card";
import {
  Skeleton,
  SkeletonCard,
  SkeletonFields,
  SkeletonList,
  SkeletonPageHeader,
  SkeletonStatRow,
  SkeletonTable,
  SkeletonTabs,
  SkeletonText,
  SkeletonToolbar,
} from "@flrc/ui/components/skeleton";
import { REPORT_KINDS } from "../reports/report-requests";

/*
 * Each admin page's loading shape, built from the shared skeleton blocks. A page shows its
 * skeleton until its first data arrives, and the router shows the same skeleton while the
 * page's code loads (route-pending.tsx), so a route change never flashes an empty area.
 * Every block is aria-hidden; the shell's PageActivity announces the load once.
 */

/** The dashboard cards fed by the summary request: term, setup problems and completion. */
export function DashboardSummaryCardsSkeleton() {
  return (
    <>
      <SkeletonCard action>
        <div aria-hidden className="space-y-4 p-5">
          <div className="flex gap-2">
            <Skeleton className="h-5 w-28 rounded-full" />
            <Skeleton className="h-5 w-28 rounded-full" />
          </div>
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-8 w-40" />
        </div>
      </SkeletonCard>
      <SkeletonCard action>
        <SkeletonList rows={4} />
      </SkeletonCard>
      <SkeletonCard action className="lg:col-span-2">
        <SkeletonTable columns={7} rows={5} />
      </SkeletonCard>
    </>
  );
}

export function DashboardSkeleton() {
  return (
    <>
      <SkeletonPageHeader meta />
      <SkeletonStatRow className="grid-cols-2" />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <DashboardSummaryCardsSkeleton />
        <SkeletonCard action>
          <SkeletonList rows={5} action />
        </SkeletonCard>
        <SkeletonCard action>
          <SkeletonList rows={5} action />
        </SkeletonCard>
      </div>
    </>
  );
}

/** The class workspace below the year bar: pickers, class tabs, teachers and the roster. */
export function ClassesBoardSkeleton() {
  return (
    <>
      <div
        aria-hidden
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 shadow-card xl:flex-row xl:items-center"
      >
        <SkeletonTabs count={GRADES.length} />
        <SkeletonTabs count={3} />
      </div>
      <div
        aria-hidden
        className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(5rem,1fr))] items-end gap-1 border-b border-border px-1 pt-1"
      >
        {Array.from({ length: 5 }, (_, index) => (
          <div key={index} className="space-y-1 rounded-t-xl bg-muted/45 px-2 py-2">
            <Skeleton className="h-4 w-10 rounded-md bg-muted-foreground/15" />
            <Skeleton className="h-3 w-14 max-w-full rounded-md bg-muted-foreground/15" />
          </div>
        ))}
      </div>
      <div aria-hidden className="flex flex-wrap items-center gap-2">
        <SkeletonTabs count={2} />
        <Skeleton className="h-9 w-24" />
        <Skeleton className="h-9 w-24" />
      </div>
      <Card aria-hidden>
        <CardBody className="space-y-3 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Skeleton className="mr-2 h-4 w-24 rounded-md" />
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-9 w-48" />
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Skeleton className="h-9 w-56" />
            <Skeleton className="h-9 w-36" />
            <Skeleton className="h-9 w-28" />
          </div>
        </CardBody>
      </Card>
      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-card">
        <SkeletonTable columns={6} rows={8} />
      </div>
    </>
  );
}

export function ClassesSkeleton() {
  return (
    <>
      <SkeletonPageHeader />
      <SkeletonToolbar />
      <ClassesBoardSkeleton />
    </>
  );
}

/** The report fields of one grade and subject. */
export function ColumnsListSkeleton() {
  return (
    <Card aria-hidden className="max-w-3xl">
      <CardBody className="divide-y divide-border">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="flex items-center gap-3 px-4 py-2.5">
            <Skeleton className="h-3.5 w-4 rounded-md" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <Skeleton className={`h-4 rounded-md ${index % 2 ? "w-1/2" : "w-2/3"}`} />
              <div className="flex gap-1.5">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>
            </div>
            <div className="flex shrink-0 gap-1">
              {Array.from({ length: 4 }, (_, button) => (
                <Skeleton key={button} className="size-7" />
              ))}
            </div>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

export function ColumnsSkeleton() {
  return (
    <>
      <SkeletonPageHeader actions={4} />
      <ColumnsListSkeleton />
    </>
  );
}

/** Teacher cards with their role drop zones, and the class tray. */
export function AssignmentsBoardSkeleton() {
  return (
    <div aria-hidden className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2 shadow-card">
          <Skeleton className="h-3.5 w-28 rounded-md" />
          <SkeletonTabs count={5} size="sm" />
        </div>
        {Array.from({ length: 3 }, (_, index) => (
          <Card key={index}>
            <CardBody className="space-y-3 p-3">
              <div className="flex items-center gap-3">
                <Skeleton className="size-9 shrink-0 rounded-full" />
                <div className="min-w-0 flex-1 space-y-1.5">
                  <Skeleton className="h-4 w-40 max-w-full rounded-md" />
                  <Skeleton className="h-3 w-56 max-w-full rounded-md" />
                </div>
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <Skeleton className="h-24 rounded-lg" />
                <Skeleton className="h-24 rounded-lg" />
              </div>
            </CardBody>
          </Card>
        ))}
      </div>
      <div className="space-y-3 rounded-xl border border-border bg-card p-3 shadow-card">
        <SkeletonText lines={2} />
        <SkeletonTabs count={5} />
        <div className="grid grid-cols-2 gap-2">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-9" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function AssignmentsSkeleton() {
  return (
    <>
      <SkeletonPageHeader />
      <SkeletonToolbar />
      <AssignmentsBoardSkeleton />
    </>
  );
}

export function LifecycleSkeleton() {
  return (
    <>
      <SkeletonPageHeader />
      <Skeleton className="h-16 w-full rounded-xl" />
      <SkeletonCard description={false}>
        <div aria-hidden className="flex flex-wrap items-end gap-3 p-5">
          <SkeletonFields count={1} className="w-full max-w-xs" />
          <Skeleton className="h-9 w-32" />
        </div>
      </SkeletonCard>
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }, (_, index) => (
          <SkeletonCard key={index} description={false} action>
            <div aria-hidden className="space-y-3 p-5">
              <div className="grid gap-2 sm:grid-cols-2">
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-8 w-28" />
                <Skeleton className="h-8 w-24" />
              </div>
            </div>
          </SkeletonCard>
        ))}
      </div>
    </>
  );
}

export function ImportSkeleton() {
  return (
    <>
      <SkeletonPageHeader />
      <SkeletonCard description={false}>
        <div
          aria-hidden
          className="grid gap-3 p-5 sm:grid-cols-[12rem_minmax(0,1fr)_auto] sm:items-end"
        >
          <SkeletonFields count={1} />
          <SkeletonFields count={1} />
          <Skeleton className="h-9 w-32" />
        </div>
      </SkeletonCard>
    </>
  );
}

export function AuditSkeleton() {
  return (
    <>
      <SkeletonPageHeader actions={1} />
      <Card aria-hidden>
        <CardBody className="grid items-end gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(5,minmax(0,1fr))_auto]">
          {Array.from({ length: 5 }, (_, index) => (
            <SkeletonFields key={index} count={1} />
          ))}
          <Skeleton className="h-9 w-28" />
        </CardBody>
      </Card>
      <Card aria-hidden>
        <SkeletonTable columns={6} rows={10} />
      </Card>
    </>
  );
}

/** The change list: a table on wide screens, cards on phones. */
export function ChangesListSkeleton() {
  return (
    <Card aria-hidden>
      <SkeletonTable columns={5} rows={8} className="hidden md:block" />
      <SkeletonList rows={6} action className="md:hidden" />
    </Card>
  );
}

export function ChangesSkeleton() {
  return (
    <>
      <SkeletonPageHeader />
      <ChangesListSkeleton />
    </>
  );
}

/** One archived class grid. */
export function ArchiveGridSkeleton() {
  return (
    <Card aria-hidden>
      <SkeletonTable columns={6} rows={10} />
    </Card>
  );
}

export function ArchiveSkeleton() {
  return (
    <>
      <SkeletonPageHeader actions={4} meta />
      <ArchiveGridSkeleton />
    </>
  );
}

export function StudentsSkeleton() {
  return (
    <>
      <SkeletonPageHeader />
      <Card aria-hidden>
        <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center">
          <Skeleton className="h-9 w-full sm:max-w-sm" />
          <Skeleton className="h-9 w-full sm:w-48" />
        </div>
        <SkeletonTable columns={3} rows={8} />
      </Card>
    </>
  );
}

/** A report kind's card: its title, class picker and whole-school request. */
function ReportKindSkeleton() {
  return (
    <Card aria-hidden className="space-y-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <Skeleton className="size-9" />
        <Skeleton className="h-5 w-24 rounded-full" />
      </div>
      <SkeletonText lines={3} />
      <SkeletonFields count={1} />
      <div className="flex gap-2">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-24" />
      </div>
      <div className="space-y-2 border-t border-border pt-4">
        <Skeleton className="h-4 w-40 rounded-md" />
        <SkeletonTabs count={2} size="sm" />
      </div>
    </Card>
  );
}

/** The kept report and export files. */
export function DownloadsListSkeleton() {
  return <SkeletonList rows={3} icon action />;
}

export function ReportsSkeleton() {
  return (
    <>
      <SkeletonPageHeader actions={1} />
      <SkeletonToolbar />
      <SkeletonText lines={1} className="max-w-xl" />
      <div className="grid gap-3 md:grid-cols-2">
        {REPORT_KINDS.map((kind) => (
          <ReportKindSkeleton key={kind} />
        ))}
      </div>
      <SkeletonCard action />
      <SkeletonCard>
        <DownloadsListSkeleton />
      </SkeletonCard>
    </>
  );
}

/** Classes shared by the teacher add form and its skeleton, so loading does not shift the layout. */
export const USERS_ADD_FORM_GRID =
  "grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto_auto]";

/**
 * Teachers & access: the add form above the teacher table, whose person column (name over
 * e-mail) takes the spare width while the selects, checkboxes, status and actions hug their
 * content.
 */
export function UsersSkeleton() {
  return (
    <>
      <SkeletonPageHeader />
      <SkeletonCard description={false}>
        <div aria-hidden className={`${USERS_ADD_FORM_GRID} p-5`}>
          {["w-full", "w-full", "w-36", "w-36"].map((width, index) => (
            <div key={index} className="grid gap-1.5">
              <Skeleton className="h-3.5 w-24 rounded-md" />
              <Skeleton className={`h-9 ${width}`} />
            </div>
          ))}
          <Skeleton className="h-9 w-36 self-end" />
        </div>
      </SkeletonCard>
      <Card aria-hidden>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
          <Skeleton className="h-4 w-40 rounded-md" />
          <Skeleton className="h-9 w-full sm:w-72" />
        </div>
        <div className="flex items-center gap-6 border-b border-border bg-muted/85 px-3 py-3">
          <Skeleton className="h-3 w-40 flex-1 rounded-md bg-muted-foreground/15" />
          <Skeleton className="hidden h-3 w-24 rounded-md bg-muted-foreground/15 md:block" />
          <Skeleton className="hidden h-3 w-24 rounded-md bg-muted-foreground/15 md:block" />
          <Skeleton className="hidden h-3 w-16 rounded-md bg-muted-foreground/15 lg:block" />
          <Skeleton className="hidden h-3 w-20 rounded-md bg-muted-foreground/15 lg:block" />
          <Skeleton className="hidden h-3 w-14 rounded-md bg-muted-foreground/15 lg:block" />
          <Skeleton className="h-3 w-16 rounded-md bg-muted-foreground/15" />
        </div>
        {Array.from({ length: 6 }, (_, index) => (
          <div
            key={index}
            className="flex items-center gap-6 border-b border-border/70 px-3 py-2.5 last:border-b-0"
          >
            <div className="grid flex-1 gap-1.5">
              <Skeleton className="h-4 w-36 rounded-md" />
              <Skeleton className="h-3 w-48 max-w-full rounded-md" />
            </div>
            <Skeleton className="hidden h-9 w-28 md:block" />
            <Skeleton className="hidden h-9 w-28 md:block" />
            <Skeleton className="hidden size-4 rounded-sm lg:mx-6 lg:block" />
            <Skeleton className="hidden size-4 rounded-sm lg:mx-8 lg:block" />
            <Skeleton className="hidden h-6 w-14 rounded-full lg:block" />
            <Skeleton className="h-9 w-40 sm:w-56" />
          </div>
        ))}
      </Card>
    </>
  );
}

/** A pupil's history: back link and header, the year/semester bar, one semester's card. */
export function StudentHistorySkeleton() {
  return (
    <>
      <div aria-hidden className="space-y-1.5">
        <Skeleton className="h-3.5 w-24 rounded-md" />
        <SkeletonPageHeader meta />
      </div>
      <SkeletonToolbar controls={3} />
      <SkeletonCard action>
        <SkeletonTable columns={2} rows={8} />
      </SkeletonCard>
    </>
  );
}
