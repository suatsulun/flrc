# ADR-077: Report sets larger than one class are background jobs with a chosen format

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-07  
**Phase:** 4.x (reports)

## Context

Whole-school report sets were rendered on the request thread (ADR-028, ADR-046). The admin had to
keep the tab open for minutes, sets queued one behind another in the browser, a finished PDF was
reachable only through a five-minute blob link, and files were named `english_middle-s7.pdf`. The
school wants any selection (one pupil to the whole school), a choice of one PDF, a ZIP with one
PDF per class, or a ZIP with one PDF per pupil, readable Turkish file names, and to leave the
page while a set is prepared.

## Decision

- **Direct downloads** stay instant: `GET /api/reports/pdf` with `class_id`, or with one or more
  `student_id` of a single class (coordinators/admins). A request without a scope is refused
  (`report_scope_required`, `report_scope_conflict`, `report_students_span_classes`,
  `student_not_in_report_set`).
- **Report jobs:** `POST /api/reports/jobs` with `{semester_id, kind, locale, format, class_ids,
student_ids}` (`format`: `combined` | `per_class` | `per_student`; both lists empty means every
  eligible class) returns 202 and a `report_set` job. The API validates the selection against the
  roster (`unknown_class`, `class_not_in_semester`, `class_not_in_report_set`,
  `student_not_in_report_set`, `empty_report_set`) and stores the output name and class count at
  creation, so the downloads list can name a job while it waits. The demo refuses jobs. An account
  may have three report jobs waiting or running at once; a fourth is refused
  (`report_jobs_pending`) under a lock on the account row, so simultaneous requests cannot pass
  together. A job the queue refuses is stored as failed (`job_queue_unavailable`, 503), not left
  waiting for a message that never comes.
- **Worker** (`reports.set`): builds the set with the fixed-query builder, renders each class once
  through the bounded pool of ADR-046 (progress counts classes), then packages it. A combined PDF
  merges classes incrementally and folds repeated fonts and covers. A per-pupil ZIP never renders
  a pupil alone: the class is rendered once — middle-school cards one per sheet instead of two-up —
  and cut by page range (two pages per duplex card, one per middle-school card). Every class's
  page count is checked against that mapping; a mismatch fails the job (`report_page_mapping`).
  A chosen class or pupil who left the set before the job ran (moved, removed, another language)
  fails it too (`class_not_in_report_set`, `student_not_in_report_set`, shown as an out-of-date
  selection), rather than a file silently missing them.
- **Output budget and numbered parts:** no stored file may pass 192 MiB. A per-class or per-pupil
  ZIP that would is cut into numbered parts, `… 1. Dönem (Bölüm 1).zip`, `(Bölüm 2)` …, breaking
  only between whole files; a pupil ZIP breaks at a class boundary when the class no longer fits
  and at most a quarter of the part would stay empty. A set that fits keeps its plain name.
  Only a single file larger than the budget, or a combined PDF (which cannot be split), fails
  with `report_output_too_large`. One part is open at a time, spooled to disk, and saved as soon
  as it closes. Outputs keep full quality: each file carries its own copy of what its pages use,
  including the school's 15–18 MB German/French back-cover PDF.
- **Storage and download:** the 24-hour `job_runs` blob of ADR-024, downloaded through
  `/api/jobs/{id}/download`. Each part is a `job_runs` row under its request (`parent_id`,
  `part`; deleted with it), so it keeps the download route and the request's authorization; parts
  stay hidden until the whole set has succeeded, then the request and every part share one
  expiry, and a failed or redelivered set discards its parts. The request of a split set has no
  blob of its own (`job_output_in_parts`). `GET /api/jobs` lists the newest 25 requests plus every
  job still running or still downloadable. `job_runs.kind` allows `report_set` and
  `year_export`; the retired per-card kinds become `report_set`, and any still waiting is failed.
- **Picker data:** `GET /api/reports/roster?semester_id&kind` lists the set's classes in print
  order with the pupils who get the card (second-language cards: only that language's pupils),
  in two queries for the whole school.
- **File names:** `{scope} {card} {year} {N}. Dönem.{pdf|zip}`, scope `8-A`, `8-A 123 Ali Yılmaz`,
  `8-A Seçili Öğrenciler`, `Seçili Öğrenciler`, `Seçili Sınıflar` or `Tüm Okul`; class sheets
  `8-A Sınıf Raporu …` / `Sınıf Raporları …`. `/` becomes `-`, characters Windows refuses are
  dropped, and `Content-Disposition` carries an ASCII `filename` plus RFC 6266 `filename*`; the
  ASCII name is cleaned again after folding, since folding turns fullwidth quotes into ASCII ones.
- **Rate limits are per route:** jobs 5/min (`report_pdf`); direct PDFs and class sheets 30/min
  (`report_single`); the year export keeps the 3/min export budget.
- **Report centre:** per card kind, View/Download one class, prepare the whole school in a chosen
  format, or pick pupils across classes; a downloads list (report and export jobs, polled while one
  runs, each poll waking the worker while a job is queued) replaces the browser queue and
  blob-link toasts. The leave guard covers only a direct download in flight.

## Alternatives considered

- Rendering each pupil separately for per-pupil ZIPs: the per-document cost ADR-028 removed.
- Cropping the two-up middle-school sheet per pupil: the other pupil's card stays in the page's
  content stream.
- Keeping whole-school sets synchronous: the tab must stay open and the request outlives proxies.
- Object storage for outputs: deferred; the budget keeps ADR-024's blob store adequate.

## Consequences

- Packaging uses pikepdf (qpdf, bundled in its wheels) rather than pypdf, and a report job
  renders each class entirely inside a render process: the process gets only that class's
  cards, renders it in batches of eight sheets (`JOB_RENDER_UNITS`), lets qpdf join the batches
  on disk, splits and covers the files the format needs, and returns only their paths. The job's
  own process builds each class's cards just before a render process can take them (two classes
  in flight with two processes) and never holds a class's PDF or HTML. A combined set's class
  files are joined from disk by qpdf and the cover goes on once, its objects shared by every
  back page; class and pupil files carry their own cover. `render.py` covers direct downloads
  with the same pikepdf helper. The render processes belong to the job and end with it, so their
  memory returns between jobs. Celery's `worker_max_memory_per_child` and
  `worker_max_tasks_per_child` act only on prefork pool children; the worker runs `--pool=solo`,
  so they would not apply and are not set.
- Measured on the 1,210-pupil local school with the private overlay and two render processes
  (peak PSS of the job's process and its render processes; the part being saved to Postgres adds
  the database driver's copy of up to one part):
  - whole-school German combined (448 pupils, 32 classes): 68 s, 65.9 MB, 838 MiB (job process
    238 MiB, render processes 405 and 403 MiB RSS);
  - middle-school English per-pupil ZIP (572 pupils, 26 classes): 75 s, three parts of
    166/166/99 MB, 718 MiB;
  - whole-school German per-class ZIP: 75 s, three parts of 188/180/147 MB, 872 MiB.
    Before the render-process change the same jobs took 334–392 s and peaked at 1.7–1.8 GiB,
    with packaging still in the job's process. The 192 MiB part size assumes the rendering above
    plus the part held twice while it is saved.
- A middle-school English pupil file is about 840 KB, almost all of it the principal's signature:
  `principals/middle.svg` embeds a 3072 × 4608 RGBA PNG that becomes a 642 KiB image plus an
  86 KiB alpha mask in every file; the school logo's 2036 × 556 JPEG adds 80 KiB; fonts and page
  content are about 15 KiB. A class PDF shares them once (22 pupils: 893 KB).
- Coordinators see report jobs in the downloads list, as `may_read_job` already allowed, and
  their own year exports; the list and the download use the same rule.
- A job freezes its classes and their pupils in one read when it starts and builds each class
  from that list. Before anything is published, every frozen pupil must appear exactly once; a
  pupil moved or removed during the job fails it with `report_roster_changed`, shown as an
  out-of-date selection, instead of being printed twice or dropped.
- Each job renders in its own temporary folder, `flrc-report-<job id>-…`. A worker reclaims
  folders of jobs that are no longer queued or running, and any folder untouched for six hours,
  when it starts and after each job, so a forced stop cannot leave pupils' PDFs on disk: the
  attempt that finishes an interrupted job also removes the folder the killed attempt left.
- A staged part carries its own six-hour expiry until the set succeeds and replaces it with the
  shared one; every class the job finishes extends it, so only a job that stopped advancing
  loses its parts. `purge_job_outputs` (nightly in the backup sidecar, or
  `flrc purge-job-outputs`) deletes parts of failed requests and staged parts past that bound,
  even when the job's own cleanup never ran, and marks a request still queued or running whose
  parts it reclaims as failed in the same transaction. A split set is published only while its
  request is still running and holds every part from 1 to the last; otherwise it fails.

## Supersedes / Superseded by

Supersedes ADR-028's "no report jobs, ZIPs or polling" and ADR-074's shared 5/min limit for class
sheets. Extends ADR-024 and ADR-046.
