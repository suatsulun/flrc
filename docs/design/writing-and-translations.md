# Writing and translations

This document covers UI copy, four-language translation resources, localized errors and the separation between interface and report wording; read this when adding a visible string, changing an API error, or working on column names and PDFs. Component and state presentation belongs in the [Design system](design-system.md).

## Voice and terminology

Write Turkish-first: establish a clear Turkish meaning, then supply idiomatic English, German and French equivalents. The interface should sound like a calm school-workflow tool, not an API client or marketing page. Follow the existing vocabulary in `packages/i18n/src/locales/tr.json`.

- Use short sentence-case labels and direct verbs: **“Kaydet”** (Save), **“Geri al”** (Undo), **“Seçimi temizle”** (Clear selection). Name dangerous actions explicitly: **“Kalıcı olarak sil”** (Delete permanently), not a vague **“Tamam”** (OK).
- Describe the record and effect, not the implementation: say which student moved, which semester is locked or what must be fixed. Avoid raw machine codes, HTTP statuses, stack traces and database terminology in ordinary messages.
- Prefer useful absence statements: **“Bu sınıfta henüz öğrenci yok.”** (There are no students in this class yet.) is more useful than a bare **“Boş”** (Empty).
- Use an ellipsis for ongoing work: **“Yükleniyor…”**, **“Kaydediliyor…”**, **“İşleniyor…”**. A completed action is past tense: **“Kaydedildi”**, **“Değişiklik geri alındı.”**
- Explain constraints without blaming the user. Pair recoverable failures with a specific next action when known; do not promise that retry can fix an authorization or locked-semester refusal.
- Translate accessible names, hints, validation messages, pending labels, empty states, file-picker faces and confirmations as carefully as visible headings.

| Domain concept                | Turkish UI wording and distinction                                                                                                                  |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Report/assessment column      | **“Sütun”**, plural **“sütunlar”**; never **“alan”** for a report column, even though backend code and older translation key names may say `field`. |
| Teaching field/role area      | **“Öğretmenlik alanı”**, **“Sorumlu alan”** remain valid; do not mechanically replace every occurrence of “alan”.                                   |
| Grade entry                   | **“Not girişi”**; a grade/score is **“not”**.                                                                                                       |
| Class workspace               | **“Sınıf tabloları”**; class report is **“Sınıf raporu”**.                                                                                          |
| Academic year / semester      | **“Eğitim yılı”** / **“dönem”**; preserve the selected year and semester in confirmation scope.                                                     |
| Undoable administration       | **“Son değişiklikler”**, action **“Geri al”**. This is not the grade audit log (**“Denetim geçmişi”**).                                             |
| Disable versus delete account | **“Devre dışı bırak”** versus **“Kalıcı olarak sil”**; the latter is irreversible. Never describe deactivation as erasing grades.                   |
| Phone grade views             | **“Kartlar”** / **“Tablo”** (Cards / Table).                                                                                                        |
| Preparatory grade             | **“Hazırlık”**; stored grade 0 is not displayed as “0. sınıf”.                                                                                      |

Use `classLabel`, `gradeLabel` and `gradeTabLabel` from `@flrc/i18n` (`packages/i18n/src/labels.ts`) for class/grade labels: named preparatory classes display their section alone; numbered classes use slash notation such as `5/A`. Do not assemble these labels independently in each screen.

Use `roleLabel` with the class or column's grade for teaching-role wording. Grade 8 English displays **Main Course teacher** and **LGS teacher**; other grades retain their existing Main/Skills labels. Mixed-grade contexts without a specific grade use **Skills / LGS teacher**. These are display labels: assignment and column ownership values remain `main` and `skills`, including in grade 8. Administrator-owned assessment titles and groups are unchanged.

### Turkish casing and language metadata

`initI18n()` in `packages/i18n/src/index.ts` installs a `languageChanged` handler before initialization and sets `document.documentElement.lang` to the resolved UI language. This affects pronunciation, hyphenation and CSS uppercase behaviour: Turkish **i → İ**, unlike English **i → I**.

- Do not hardcode `lang="tr"` on a shared page or force Turkish casing for English/German/French UI text.
- Keep source strings in natural case; let existing heading styles handle visual uppercase. When transforming user text in JavaScript, choose locale-aware casing deliberately rather than assuming `toUpperCase()` is correct for Turkish.
- A Turkish wording input may correctly use `lang="tr"` even in another UI language; see `ClassAddColumn.tsx` and `routes/_auth/columns.tsx` in the admin app.
- Use `i18n.language`/the resolved language for locale-sensitive display formatting, not a fixed Turkish date or decimal formatter on a shared screen.
- Do not alter person names for presentation. Public examples, screenshots and fixtures must contain synthetic data only.

## Resource structure and runtime behaviour

The files are `packages/i18n/src/locales/{tr,en,de,fr}.json`. Each is one nested JSON object loaded into the **`common`** namespace; calls use dotted keys such as `t("users.title")`, not a namespace per screen.

| Key family                                                              | Responsibility                                           |
| ----------------------------------------------------------------------- | -------------------------------------------------------- |
| Root keys such as `loading`, `logout`, `goToAdmin`                      | Small shared interface vocabulary                        |
| `shell.*`, `feedback.*`                                                 | Navigation, theme controls and generic action status     |
| `adminDashboard.*`, `classWorkspace.*`, `roster.*`, `assignmentBoard.*` | Screen/workflow-specific copy                            |
| `grid.*`, `classReport.*`, `reports.*`                                  | Grade entry, class sheet and report-generation workflow  |
| `subjects.*`, `roles.*`, `teachingStages.*`, `lifecycle.*`              | Localized labels for machine enum values                 |
| `errors.codes.*`                                                        | Business-rule/API machine-code messages                  |
| `auth.errors.*`, `reports.errors.*`                                     | Authentication and report-request-specific error wording |
| `changes.*`, `changes.blocked.*`                                        | Recent changes, Undo and contextual refusal messages     |

Runtime configuration uses `fallbackLng: "tr"`, supported languages `tr`, `en`, `de`, `fr`, `load: "languageOnly"` and `nonExplicitSupportedLngs: true`. Regional browser settings such as `en-GB` resolve to the supported base language. `LanguageSwitch` shows TR/EN/DE/FR; do not invent another language menu or assume the browser locale is already a supported code.

`interpolation.escapeValue` is false because React handles escaping ordinary rendered strings. This is not permission to inject translation text as HTML. Interpolate values with `{{name}}`, `{{count}}`, etc.; do not concatenate translated sentence fragments whose grammar or word order can differ between languages.

### Adding or changing a key

1. Find the existing semantic family and reuse a suitable key if its meaning truly matches. Otherwise add a descriptive nested key there; do not encode English prose or route URLs into key names.
2. Add the same leaf key to **all four** locale files in the same change. Keep interpolation placeholders and their meaning consistent in every translation. JSON uses two-space indentation; avoid duplicate object keys.
3. Use `useTranslation()` in React components, then `t("family.key", { name, count })`. Shared UI primitives usually accept labels as props so they remain independent of i18n; see `ThemeToggle`, `AcademicContextBar` and `FilePicker`.
4. Reuse `appShellLabels(t)` and `academicContextLabels(t, locked)` from `packages/i18n/src/labels.ts` for their corresponding shared component contracts.
5. For runtime-generated keys, enumerate the valid values. If adding a new dynamic enum family/value, extend `requiredDynamicKeys` in `scripts/check-i18n.mjs` where appropriate; literal scanning cannot discover arbitrary template expressions.
6. Run from the repository root:

   ```sh
   pnpm i18n:check
   ```

7. Inspect the actual screen in each supported language, including long German/French labels, phone wrapping, accessible names and Turkish uppercase. Key presence is not proof of grammatical correctness or visual fit.

The root command runs `node scripts/check-i18n.mjs`. The checker flattens all resource keys, compares every locale with English, detects duplicate formatted keys, scans literal `t(...)` calls in `apps/admin/src`, `apps/teacher/src` and `packages/ui/src`, and checks an explicit dynamic-key list. It does **not** validate translated meaning, placeholder parity, every computed key, layout, or copy embedded outside its source roots. Review these separately.

### Counts: no automatic plural families

The repository's resources use count-neutral wording, not i18next plural suffix families. Do not add `_one`, `_other`, `_few`, etc. or assume that passing `{ count }` creates the missing forms. Use one complete sentence that works for every count, including zero and one.

Examples already in the resources:

- Turkish `assignmentBoard.classCount`: `"{{count}} sınıf"`.
- Turkish `roster.selected`: `"{{count}} seçildi"`.
- Turkish `adminDashboard.term` and completion copy distinguish missing data through explicit states rather than pretending a loading count is zero.

Choose a naturally count-neutral construction in each language rather than mechanically copying Turkish noun structure. The `_student`, `_field`, `_slot`, etc. suffixes under `changes.blocked` are **i18next context variants**, not plurals; preserve them with the base message.

## Feedback, confirmation and error patterns

### Toasts and pending text

Prefer a meaningful outcome over generic success: `roster.numberSaved` names the student and number, `classWorkspace.studentMoved` names the destination, and `assignmentBoard.assigned` names the teacher, class and role. Use `feedback.actionSucceeded` only when no more specific message is appropriate.

Pass a translated `pendingLabel` to shared pending buttons. Pending text describes work in progress, not a promise of completion. A queued report uses `reports.jobQueued`; it is not yet a downloaded or completed PDF.

For recorded admin writes, call `useNotifyDone` from `apps/admin/src/admin/undo-toast.ts` with the specific message and response `action_id`. This is the shared path for the **“Geri al”** action; do not write your own toast-only Undo or claim permanent deletion can be undone. Interaction timing and retention are specified in the [Design system](design-system.md#state-and-interaction-contract).

### Confirmations

A confirmation must name the action and target, state its scope and distinguish removal from destruction. Existing resources provide examples:

| Pattern                           | Resource/example                                                                                                                          |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Clear irreversible title          | `users.deleteTitle`: `"{{name}} kalıcı olarak silinsin mi?"`                                                                              |
| Explicit irreversible consequence | `users.deleteDescription`: `"Bu işlem geri alınamaz. Hesap bir daha giriş yapamaz."`                                                      |
| Countdown button                  | `users.deleteCountdown`: `"Kalıcı olarak sil ({{seconds}})"`                                                                              |
| Preserve-history explanation      | `classWorkspace.removeStudentConfirm` explains the year/class enrollment removed and the identity, saved grades and other years retained. |
| Move explanation                  | `classWorkspace.moveConfirmOne`, `moveConfirmMany`, `moveKeeps` explain source, destination and what moves together.                      |
| Specific locked-state error       | `errors.codes.semester_locked`: `"Bu dönem kilitli olduğu için değişiklik yapılamaz."`                                                    |

Do not hide important effects in a tooltip or use a generic “Are you sure?” for a multi-record operation. Use the site's translated `ConfirmDialog`/`CountdownConfirmDialog` labels; avoid native `alert()`/`confirm()` as application copy surfaces. Preserve the actual browser `beforeunload` warning where required: its wording belongs to the browser.

### API error → localized message

Backend errors are machine data. The admin mapping lives in `apps/admin/src/admin/feedback.ts`:

1. `apiError(error)` reads generated-client `{ detail: { code, reason?, params? } }`. Validation arrays become `invalid_request`; unknown shapes have no code. Only string/number params are retained.
2. `localizeParams` converts machine roles, subjects and grade levels into display labels.
3. `errorMessage(error)` handles `undo_blocked` first: prefer `changes.blocked.<reason>` with the record-specific i18next context, then `errors.codes.<reason>`.
4. For ordinary errors, use `errors.codes.<code>` if present; otherwise use `feedback.actionFailed`.

When introducing a business-rule code, add a human-readable `errors.codes.<code>` in all four locales and preserve its interpolation contract. Never expose server exception text as a fallback. Undo refusal contexts are selected from params (`student`, `field`, `user`, `class`/`role`, `grade_level`, `count`); a specific variant must retain its base fallback.

Some features have their own richer mappings: `apps/admin/src/reports/report-errors.ts` maps report-request failures, and the teacher grid has translated rejection/conflict states rather than treating every save response as a single successful write. Reuse the feature's established path; do not replace partial-success/conflict handling with a generic toast.

## UI language, assessment names and PDF language are different

[ADR-013](../adr/013-i18n-from-first-component.md) separates deployed interface strings from administrator-owned report wording. Do not store custom assessment names in the static UI JSON or persist an i18n key as the displayed name.

| Layer                                      | Source of wording and language choice                                                                                                                                                                                                                                         |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| App chrome                                 | Four `packages/i18n` resources and the user's UI language.                                                                                                                                                                                                                    |
| Assessment column/group name shown in apps | Stored `ColumnDefinition.labels`/`group_labels`, resolved in the subject's language, independent of UI language. `SUBJECT_LOCALE` in `apps/backend/src/flrc/modules/academics/fields.py` maps English → `en`, German → `de`, French → `fr`; `field_name()` uses this mapping. |
| Required Turkish report wording            | Column creation accepts `name`/`group` in the subject language and `turkish_name`/`turkish_group` where the printed bilingual card needs them. See `apps/backend/src/flrc/modules/academics/columns.py`.                                                                      |
| Report request locale                      | `apps/admin/src/routes/_auth/reports.tsx` has a separate report-language `Segmented`, state initialized to `tr`, passed to report requests. Changing this does not change the UI locale.                                                                                      |
| Printed assessment labels                  | `bilingual_field()` in `apps/backend/src/flrc/modules/reports/builder.py` carries Turkish and the subject-language labels; the report template decides where each appears. These fixed bilingual labels do **not** switch to the caller's UI language.                        |

`pick_label()` in `academics/fields.py` falls back through requested locale, base language, Turkish, then any non-empty stored label. Do not substitute the UI language for the subject language to make column headings follow the language switch. This was deliberately changed in [ADR-072](../adr/072-fields-are-named-in-their-subject-s-language.md).

Column names can now be edited through the subject-language `name`; Turkish wording, group names and other labels stay as created ([ADR-076](../adr/076-field-names-can-be-edited-after-creation.md)). Do not repeat ADR-072's superseded statement that names cannot be edited. Do not assume every custom column requires four administrator-entered translations: the current creation API takes subject-language wording plus Turkish where required.

For PDF template/rendering structure and job behaviour, use [Reports and jobs](../architecture/reports-and-jobs.md); this document owns only the wording/language boundary.
