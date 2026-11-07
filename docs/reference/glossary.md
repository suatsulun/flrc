# Glossary

This glossary maps Turkish school/UI vocabulary to English meanings and repository identifiers. Read this when naming a feature, translating a screen or interpreting assessment/report code; implementation details belong in the linked architecture documents.

## School, academic context and people

| Turkish term                               | English meaning                         | Code / usage                                                                                                                                                                     |
| ------------------------------------------ | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| “karne”                                    | Report card                             | `ReportCard`; report kinds `english_elementary`, `english_middle`, `german_karne`, `french_karne`. Not a year-export workbook.                                                   |
| “sütun”, “değerlendirme sütunu”            | Assessment/report column                | `ColumnDefinition`, `column_definitions`, `column_id`. Use **sütun**, not “alan”, in Turkish UI for these columns. Existing internal `field` names do not change that copy rule. |
| “eğitim-öğretim yılı”                      | Academic year                           | `AcademicYear`, `year_id`, `year_label`; statuses setup/active/archived                                                                                                          |
| “dönem”                                    | Semester/term                           | `Semester`, `semester_id`, `semester_number`; number 1 or 2, open/locked                                                                                                         |
| “Hazırlık”                                 | Preparatory grade                       | `PREP_GRADE`, `grade_level=0`; named sections, part of primary school                                                                                                            |
| “sınıf seviyesi”                           | Grade level                             | `grade_level` 0–8, not a score                                                                                                                                                   |
| “sınıf”, “şube”                            | Class/section                           | `SchoolClass`: one year's grade and section; `class_id`. `section` is the letter or name, e.g. `A`; display combines grade/section, e.g. `5/A`.                                  |
| “ilkokul”                                  | Primary school stage                    | `primary`: Hazırlık through grade 4; `english_elementary` is the primary English report kind                                                                                     |
| “ortaokul”                                 | Middle school stage                     | `middle`: grades 5–8; `english_middle` report kind                                                                                                                               |
| “öğrenci”                                  | Student/person                          | `Student`, stable `student_id` across school years                                                                                                                               |
| “kayıt”, “sınıf kaydı”                     | Yearly enrollment/placement             | `Enrollment`: student + academic year + class; distinct from a grade-save record                                                                                                 |
| “okul numarası”                            | School number                           | `Enrollment.school_number`, unique per year and stage, not a stable person ID                                                                                                    |
| “ikinci yabancı dil”                       | Second foreign language                 | `StudentLanguage.language`: `german` or `french`, per student/year                                                                                                               |
| “İngilizce”, “Almanca”, “Fransızca”        | English, German, French                 | Subjects/teaching fields `english`, `german`, `french`; UI locale codes are instead `en`, `de`, `fr`                                                                             |
| “öğretmen”                                 | Teacher                                 | `User`; ordinary authenticated account without admin/coordinator privileges                                                                                                      |
| “sınıf öğretmeni”                          | Main English teacher/responsibility     | Assignment/column-owner role `main`; not an unrestricted global user role                                                                                                        |
| “beceri öğretmeni”                         | English skills teacher/responsibility   | Assignment/column-owner role `skills`                                                                                                                                            |
| “Almanca öğretmeni”, “Fransızca öğretmeni” | Second-language teaching responsibility | Assignment/column-owner role `german` / `french`                                                                                                                                 |
| “koordinatör”                              | Coordinator                             | `User.is_coordinator`; oversight/report privileges, not all admin writes                                                                                                         |
| “yönetici”                                 | Administrator                           | `User.is_admin`; management permission enforced in the API                                                                                                                       |
| “ders alanı”                               | Account teaching field                  | `User.teaching_field`; this is not an assessment “sütun”                                                                                                                         |
| “öğretim kademesi”                         | Account teaching stage                  | `User.teaching_stage`; required primary/middle for English, null for German/French                                                                                               |
| “öğretmen ataması”                         | Teaching assignment                     | `TeachingAssignment`: class + role → teacher                                                                                                                                     |

See [data model](../architecture/data-model.md) for identity/placement constraints and [authentication](../architecture/auth-and-sessions.md) for role semantics. Stage-scoped numbers follow [ADR-070](../adr/070-school-numbers-are-unique-per-stage.md); grade 0 follows [ADR-065](../adr/065-hazirlik-classes-are-grade-0-with-named-sections.md).

## Assessment and UI actions

| Turkish term                            | English meaning                              | Code / usage                                                                           |
| --------------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------- |
| “not”, “puan”                           | Numeric score or saved assessment in context | `GradeValue`; numeric `score` is 0–100. Do not treat every grade value as numeric.     |
| “değerlendirme”, “1-2-3 ölçeği”         | Three-point rubric rating                    | `value_type="scale3"`, `GradeValue.scale`; null means no rating                        |
| “Geliştirilmeli”                        | Needs improvement                            | Rating 1; `grid.scaleLevels.1`, `SCALE3_FACES[1]`                                      |
| “İyi”                                   | Good                                         | Rating 2; `grid.scaleLevels.2`, `SCALE3_FACES[2]`                                      |
| “Çok iyi”                               | Very good                                    | Rating 3; `grid.scaleLevels.3`, `SCALE3_FACES[3]`                                      |
| “öğretmen görüşü”, “öğretmen görüşleri” | Teacher comment/opinion                      | `value_type="text"`, `text_value`; not present as active English columns in grades 5–8 |
| “ortalama”                              | Average                                      | `ColumnDefinition.counts_in_average`; only applicable score columns participate        |
| “kategori”                              | Assessment grouping                          | `group_labels`; `assessment-filter.ts` / `assessment-filters.tsx`                      |
| “Tablo”                                 | Table/grid presentation                      | Teacher route view `grid`; `GridTable` / grid keyboard navigation                      |
| “Tek öğrenci”                           | Single-student presentation                  | Teacher route view `stepper`; `StepperView`, same drafts/save pipeline                 |
| “Kaydet”                                | Save drafts                                  | `useSaveGrid`, `save_grid`; not an automatic write on every keystroke                  |
| “Son kaydı geri al”                     | Undo last grade save                         | `undo_grid`, `SaveBatch`; distinct from administrative-action undo                     |
| “Son değişiklikler” / changes screen    | Recent administrative edits                  | `AdminAction`, `listAdminActions`, `undoAdminAction`; seven-day undo system            |
| “salt okunur”                           | Read-only                                    | Locked semester/archived context; draft UI and API must respect writable state         |
| “Sınıf Raporu”                          | Class report/sheet                           | `class_sheet.py`, `getClassSheet`, printable middle-school English overview            |
| “ÖNİZLEME”                              | Preview watermark                            | `PREVIEW_WATERMARK`, `get_report_preview`; not an issued official card                 |
| “indirilenler” / downloads list         | Available generated files and requests       | `DownloadsList`, `JobPartsList`, `JobOut`                                              |
| “Bölüm” in a download name              | Numbered archive part                        | `JobRun.parent_id`, `part`; separate ZIP downloads under one request                   |

The 1–3 labels above are the Turkish UI's shared labels; printed reports also have subject-specific bilingual wording/order. Keep rating values stable even when labels or presentation change. See [frontend](../architecture/frontend.md) and [reports and jobs](../architecture/reports-and-jobs.md).

## Project terms

| Term                               | Meaning / code                                                                                                                                                           |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Allowlist                          | Existing active `users` row admitted by the school's Google/domain policy; not automatic domain-wide account creation                                                    |
| Assignment ownership               | Responsibility for a class's owner role; controls grade-save warnings/confirmation, not school-wide grid discovery                                                       |
| Override grant                     | One-hour renewable user/class/role permission (`OverrideGrant`) for audited collaboration outside the assigned role                                                      |
| Save batch                         | One applied grade-save action (`SaveBatch`) grouping atomic grade writes and `AuditEntry` snapshots                                                                      |
| Optimistic concurrency             | Client submits `expected_version`; stale versions produce conflicts unless explicitly forced                                                                             |
| Dirty map / draft                  | Unsaved browser edits in Zustand `useDirtyStore`, keyed `studentId:columnId`; separate from Query's confirmed data                                                       |
| Draft generation                   | `useDirtyStore.generation`; invalidates late save responses after discard/navigation so they cannot restore old drafts                                                   |
| Admin action                       | Undoable administrative snapshot (`AdminAction`), not a grade batch or general-purpose permanent audit log                                                               |
| Report identity                    | A teacher's printed `report_name`, signature PNG and digest; changes recorded in `ReportIdentityAudit`                                                                   |
| Overlay                            | Read-only deployment-supplied branding/report assets and optional templates under `SCHOOL_BRANDING_DIR`; private institutional identity does not belong in public source |
| Report set                         | Eligible collection for one report kind/semester; direct for one class, background `report_set` for larger selections                                                    |
| Combined / per class / per student | Packaging values `combined`, `per_class`, `per_student`; one PDF or ZIP(s) of class/student PDFs                                                                         |
| Job                                | Durable `JobRun` state/output; Redis is its queue, not its status database                                                                                               |
| Golden baseline                    | Pristine seeded demo parent branch (`NEON_GOLDEN_BRANCH_ID`) used to restore the mutable public-demo branch; not real school data or a backup of the school              |
| Demo visitor                       | Pseudonymous temporary admin/coordinator linked by keyed Google-subject hash in `DemoVisitor`; shared synthetic school, not a separate visitor tenant                    |
| Rollover                           | Year-close creation of next setup year's eligible structure/placements; never a copy of grade values/history                                                             |
| Same-origin proxy                  | Browser uses its own `/api/*`; gateway forwards to FastAPI while keeping host-only cookies first-party                                                                   |
| Panel switch                       | Full-document navigation between separate teacher and admin SPAs, role-gated in the UI but authorized by API guards                                                      |
| Skeleton                           | Noninteractive loading shape matching destination content; route maps are exhaustive over generated route IDs                                                            |
| ADR                                | Architecture Decision Record under `docs/adr`; preserves numbered rationale, with later decisions able to supersede earlier ones                                         |

Administrative undo is [ADR-075](../adr/075-admin-changes-can-be-undone-for-seven-days-and-conflicts.md), background sets are [ADR-077](../adr/077-report-sets-larger-than-one-class-are-background-jobs-with-a.md), skeletons are [ADR-081](../adr/081-everything-that-loads-shows-a-skeleton-shaped-like-its.md), and phone cards are [ADR-082](../adr/082-phones-get-card-layouts-not-sideways-scrolling-tables.md). Begin with the [architecture overview](../architecture/overview.md) for a source map.
