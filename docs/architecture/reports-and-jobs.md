# Reports and jobs

Reports turn saved assessments into printable cards, class sheets and year workbooks. Read this when changing report eligibility, PDF rendering, packaging, download authorization or worker behavior; table definitions are in the [data model](data-model.md).

## Report surfaces

| Surface/kind                   | Scope and implementation                                                                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `english_elementary`           | Hazırlık (grade 0) through grade 4 English; bilingual primary progress card                                                                      |
| `english_middle`               | Grades 5–8 English progress card; normally two A5 cards imposed on an A4 sheet                                                                   |
| `german_karne`, `french_karne` | Grades 1–8 eligible students taking that year's matching second language; bilingual karne                                                        |
| Class report/sheet             | Middle-school English parent-meeting view and one-page-per-class printable sheet; `reports/class_sheet.py`, teacher `src/class-report/`          |
| Card preview                   | One student's real card with “ÖNİZLEME” (preview) diagonally stamped on every page; `reports/preview.py`                                         |
| Year export                    | Seven-sheet XLSX workbook of yearly students, enrollments, languages, assignments, columns, grades and audit history; `workers/tasks/exports.py` |

`builder.py:REPORT_SETS` defines card eligibility. Do not infer eligible grades from the UI's language picker: report specifications and current programme column rules are distinct. Grade 4 German/French have ratings/comments rather than numeric scores; middle-school English excludes teacher-opinion text. See [programme rules](data-model.md#columns-and-programme-rules).

`GET /api/reports/pdf` is for a single class, or selected students belonging to one class. It requires coordinator/admin access. A request with no scope, both class and student scope, or students spanning classes is rejected. `GET /api/reports/roster` returns eligible classes/students in report order.

Any authenticated teacher may obtain middle-school English class sheets (`GET /api/reports/class-sheets`), independently of assignment ownership ([ADR-074](../adr/074-middle-school-english-teachers-print-one-page-class-sheets.md)). Card preview is stricter: teachers may preview only cards produced by their own assignments in that student's enrollment year; admins/coordinators can preview all eligible cards. Override grants do not expand preview scope. A middle-school preview crops the two-up sheet to the one populated top card ([ADR-078](../adr/078-teachers-preview-their-own-students-report-cards-on-screen.md)).

## Rendering pipeline

```text
PostgreSQL → builder.py → ReportEntry/ReportCard DTOs
           → Jinja2 HTML templates → WeasyPrint → ordered PDF assembly/cover/watermark
```

`reports/builder.py` joins enrollment, semester definitions, saved values and assigned teachers' report identities. Roster ordering uses school number (null last), normalized name and stable ID; classes use grade/section order. Browser drafts never enter the renderer.

`reports/render.py` owns template selection, geometry, imposition, assets, worker sizing and finished-PDF operations. Templates live in `reports/templates`; built-in assets in `reports/assets`. Direct API rendering is dispatched through `run_in_threadpool`, not run on the async event loop. Native WeasyPrint dependencies are installed by the backend Dockerfile.

`ReportAssetFetcher` permits only application-created `data:` URIs and denies file/network fetching. Private report overlays use contained paths, sandboxed/autoescaped Jinja and explicit DTO context; do not weaken these boundaries to load arbitrary URLs. School-specific templates, principal identities and artwork remain in the school's private deployment repository, while teacher names/signatures are database-managed. Overlay layout is documented in [branding](../operations/branding.md), following [ADR-057](../adr/057-private-report-overlays-and-teacher-report-identities.md).

### Bounded parallelism

`render_worker_limit()` honors explicit `REPORT_RENDER_WORKERS`; zero auto-sizes from usable CPUs/container quota with an automatic cap of four. An explicit positive setting is a hard requested count, not clamped to four—size it for memory as well as CPU.

Direct report rendering goes parallel only from 12 layout units; batches are at most 16 units. It keeps no pool: each wave starts one `forkserver` process per document, each with its own pipe; the parent reads every pipe to end of file, and every process is stopped and joined and every pipe closed before the render returns, so no process outlives the document or keeps a teacher's signature ([ADR-080](../adr/080-a-deactivated-teacher-can-be-deleted-permanently-their-grade.md)). Concurrent renders in one OS process share a budget of `render_worker_limit()` processes, reserved before a wave starts and released once its processes have exited. A parallel render still running after ten minutes (`RENDER_DEADLINE_SECONDS`) stops its processes, gives the budget back and fails (`report_render_timed_out`); a process that exits without its whole PDF, or a host that cannot start processes, falls back to bounded serial rendering in output order. Background packaging has a **per-job** pool; each class renders in its own process with smaller eight-unit batches, and processes exit with the job. Do not render one whole-school WeasyPrint page tree or retain all class DTOs/PDF byte copies at once. See [ADR-046](../adr/046-parallel-class-rendering-with-ordered-pdf-assembly.md) and [ADR-077](../adr/077-report-sets-larger-than-one-class-are-background-jobs-with-a.md).

## Background report sets

`POST /api/reports/jobs` returns 202 with a durable `JobOut`. Empty `class_ids` and `student_ids` select the whole eligible school; supply one selection kind, never both. The request validates the semester, year and eligibility before recording a queued `report_set` row and sending `reports.set` to Celery. An account may have three report jobs waiting or running at once (split-part rows do not count); a fourth is refused with 409 `report_jobs_pending`, checked under a lock on the account row so simultaneous requests cannot pass together. A job the queue refuses is stored as failed and answered 503 `job_queue_unavailable`, not left waiting for a message that never comes. Public-demo mode rejects background report jobs (`demo_report_class_required`); use direct class reports there.

Formats are:

| `format`      | Output                                                               |
| ------------- | -------------------------------------------------------------------- |
| `combined`    | One combined PDF, assembled in print order                           |
| `per_class`   | ZIP containing one PDF per class                                     |
| `per_student` | ZIP containing one PDF per student, with independent printable cards |

At execution start, `run_report_job` freezes the selected roster IDs, then builds classes lazily as renderer capacity becomes available. Progress counts completed classes. A chosen class or pupil who left the set before the job ran (moved, removed, another language) fails it with `class_not_in_report_set` or `student_not_in_report_set`, rather than a file silently missing them. Before publishing, it confirms every frozen pupil was printed exactly once; a roster change that breaks that set fails with `report_roster_changed`. The report centre shows all three as an out-of-date selection. This is not a snapshot of every grade at enqueue time: report data is built while the job runs.

A redelivered task discards old staged parts and starts again; an already succeeded job is not rerendered. Expected packaging failures record their stable code; unexpected failures record `report_set_failed`. Job state lives in PostgreSQL; Redis only delivers the message. The API optionally pings `WORKER_HEALTH_URL` on enqueue and, while a job is queued, on each poll of the job list and job status to wake a sleeping managed worker. See [backend worker configuration](backend.md#workers-and-cli).

## Output bounds and file naming

`packaging.py:MAX_OUTPUT_BYTES` is **192 MiB per stored file**. ZIP construction spools to disk beyond 8 MiB and publishes numbered parts only between complete PDF entries. A combined PDF or a single PDF entry larger than the limit fails with `report_output_too_large`; the renderer does not truncate it. Combined class PDFs are assembled from disk with qpdf/pikepdf rather than retaining an unbounded in-memory merge.

Numbered parts are child `job_runs` rows. While staging, they remain hidden as running and have a six-hour safety expiry, which every class the job finishes extends, so only a job that stopped advancing loses its parts. A split set is published only while its request is still running and holds every part from 1 to the last; otherwise it fails. Once the whole set succeeds, parent and parts receive the shared successful expiry. A failed set discards its parts; no partial successful download is exposed.

`reports/filenames.py` is the naming authority. Names retain Turkish words/letters regardless of UI locale, replace class `/` with `-`, and remove unsafe/control characters. Examples with synthetic scope:

- `8-A İngilizce Karne 2026-2027 1. Dönem.pdf`
- `Tüm Okul Almanca Karne 2026-2027 1. Dönem.zip`
- `Tüm Okul Almanca Karne 2026-2027 1. Dönem (Bölüm 2).zip`
- `8-A Sınıf Raporu 2026-2027 1. Dönem.pdf`

Student filenames add class, available school number and student name; ZIP collisions receive distinct names rather than overwriting an entry. `Content-Disposition` supplies an ASCII fallback, cleaned again after folding (folding turns fullwidth quotes into ASCII ones), plus UTF-8 `filename*`. Direct PDFs are inline; stored-job downloads are attachments. Client delivery helpers are shared under `packages/ui/src/lib/file-delivery.ts`.

## Downloads, exports and retention

`GET /api/jobs` returns recent requests **plus every still-running or still-downloadable job/part**, not merely the newest page. `GET /api/jobs/{id}` supplies durable status; `/download` loads the deferred blob only when needed. Admins may read all jobs, requesters their own, coordinators all non-year-export jobs. These checks apply to parts too.

Successful outputs last **24 hours** from completion in PostgreSQL, not the API/worker filesystem ([ADR-024](../adr/024-completed-job-output-is-a-short-lived-postgres-blob.md)). Download refuses unfinished jobs with 409, split parents with `job_output_in_parts`, and absent/expired blobs with 410 `output_expired`. `DownloadsList.tsx` and `JobPartsList.tsx` render the request and its downloadable parts in the admin report centre.

`POST /api/exports/year/{year_id}` is admin-only and queues `year_export`. The worker streams query rows and write-only workbook XML, commits progress between closed cursors and emits `flrc-year-{year_id}.xlsx`. Spreadsheet values pass `safe_spreadsheet_cell`; never bypass formula-injection protection. A year workbook is an application export, **not** a substitute for database backups or a restore-tested archive; see [backups and restore](../operations/backups-and-restore.md).

`flrc purge-job-outputs` removes expired blobs while retaining request metadata and removes failed/expired staged parts; a request still queued or running whose parts it reclaims is marked failed in the same transaction. Job temporary directories are scoped by `flrc-report-{job_id}-`; a worker reclaims abandoned workspaces when it starts and after each job, using live job IDs and a six-hour stale bound, so the attempt that finishes an interrupted job also removes the folder the killed attempt left. Durable outputs must never depend on these temporary files. Retention scheduling belongs in the [runbook](../operations/runbook.md).

## Limits

Limits come from `core/rate_limit.py`, report request models and class-sheet query bounds. Rate windows are 60 seconds and per-account:

| Operation                                                          | Budget/bound                                                                        |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Background report-set requests                                     | 5/minute                                                                            |
| Direct class/student PDFs, class sheets and previews               | Shared single-report scope, 30/minute                                               |
| Year export and other bulk-export routes using `export_rate_limit` | 3/minute                                                                            |
| Direct selected students                                           | At most 100 IDs and one class                                                       |
| Background selection                                               | At most 200 class IDs or 2,000 student IDs; empty lists select all eligible classes |

A rate-limited response is 429 with `Retry-After`. Do not retry expensive work in a tight polling loop; poll status, not the creation route. OAuth and import budgets are separate; see [authentication](auth-and-sessions.md) and [backend](backend.md).
