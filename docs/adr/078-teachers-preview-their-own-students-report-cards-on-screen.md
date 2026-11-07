# ADR-078: Teachers preview their own students' report cards on screen, watermarked

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-07  
**Phase:** 4.x (reports)

## Context

Teachers could not see a finished report card before the school printed the official set: only
coordinators and administrators download card sets. Mistakes in grades or wording surfaced on
paper. Teachers asked to check their students' cards themselves, one by one, without being able
to hand out an unofficial copy.

## Decision

- The teacher panel's class report section has two modes, "Sınıf raporu | Karne önizleme".
  Karne önizleme lives at `/card-preview`: pick one of the teacher's classes (with its card), then
  a student from the class list or with Previous/Next and the ←/→ keys (ignored while a form field
  has focus). A position indicator ("5 / 22") shows where the teacher is. The PDF is shown in an
  iframe from a `blob:` URL with `#toolbar=0&navpanes=0`, and each URL is revoked when the next
  card replaces it or the page closes. There are no download or print buttons.
- `GET /api/reports/preview/scope?semester_id=` lists the classes where the signed-in user holds a
  teaching assignment in that semester's year (without `semester_id`: the class catalog's current
  term), each with its card kind and its students in the official set's order, plus the year's
  semesters. Administrators get their own assignments too; the admin report centre covers the rest.
- `GET /api/reports/preview?semester_id&student_id&kind` returns one student's card as an inline
  PDF. Authorization is stricter than grade reads (ADR-071) because a card is one student's
  complete record: a teacher may preview only the card their own assignment in the student's class
  produces in that year — main or skills give the English card for the grade (elementary or
  middle), german or french give that karne and only for students taking the language.
  Administrators may preview any card that exists; everyone else, coordinators included, gets 403.
  A pupil outside the teacher's classes is a 403, never a 404, so the endpoint reveals nothing.
- The preview is the real card: the official builder builds just that student's card, picked by
  student id (never by name or roster position, which two unnumbered pupils of a setup year can
  share), and the same templates, overlays and back covers render it. `render_report_pdf`
  takes an optional keyword-only `watermark`; with it, a diagonal "ÖNİZLEME" is stamped over every
  finished page (each card of a two-up sheet, back covers included) as a PDF overlay, so private
  template overlays need no change. Official sets never pass it and render exactly as before. The
  middle-school English card, imposed two to an A4 sheet, is cropped to its own A5 half, so a
  preview never shows a blank or another pupil's card slot.
- Previews share the single-report limit (`report_single_rate_limit`, 30 per minute per account).
  The viewer waits for paging to settle before requesting a card and shows the server's
  `Retry-After` as "wait N seconds" when limited. Responses are `no-store`.
- Teachers who cannot use class sheets (anything but middle-school English) get a "Karne önizleme"
  sidebar entry instead; the class-sheet entry and its limits are unchanged. The mode switch is
  shown wherever both modes are available.
- The web CSP gains `frame-src 'self' blob:`; without it browsers block the `blob:` iframe.
- Class-sheet download and print use the shared file-delivery helpers: the server's file names,
  a print tab opened during the click (the file is saved instead if that tab is gone), a leave
  guard while a PDF is in flight, and the `Retry-After` wait in the rate-limit message.

## Alternatives considered

- Let teachers download the official card set for their classes: copies would leave the school
  without the review step, and a set costs the whole-set rate limit.
- Watermark through the templates: private overlays and the original back-cover PDFs would print
  without it, and every template would carry preview-only markup.
- A server-rendered image per page: hides the text layer but needs a rasteriser in the image and
  is slower and blurrier than the browser's PDF viewer.

## Consequences

- A determined teacher can still save the iframe's PDF or screenshot it; the watermark, not the
  missing buttons, keeps such a copy from passing for an issued card.
- Every preview renders one card on the request thread; paging through a 30-pupil class fits the
  per-minute limit only because the viewer waits for paging to settle.
- Deployments with their own proxy configuration must add `frame-src 'self' blob:` to their CSP.

## Amendment (2026-11-07): the report section for everyone, school-wide previews

The school owner asked that every teacher-panel user reach both report views, and that the people
who oversee the school check any card from the teacher panel instead of downloading sets.

- The teacher sidebar always has a "Raporlar" section with "Sınıf raporu" and "Karne önizleme";
  both pages carry the mode switch. This replaces the rule above that teachers without class
  sheets get only Karne önizleme, and ADR-074's rule that only middle-school English teachers see
  the class-sheet entry (its endpoint already served every authenticated user).
- Sınıf raporu opens the middle-school English class on screen; otherwise `/class-report` opens
  the user's own middle-school English class, else the year's first one. A year without any such
  class shows an explanation instead.
- `GET /api/reports/preview/scope`: administrators **and coordinators** get every class of the
  year with every card it has — the English card of its grade, and the German or French karne
  when at least one of its pupils takes that language. Teachers still get only the classes they
  hold an assignment in; a teacher without one gets an empty scope, which the page explains.
- `GET /api/reports/preview`: coordinators join administrators: any existing card, 404 for an
  unknown pupil and 409 for a card the pupil does not get. Teachers keep the 403-only rule, and
  the watermark, crop, id-based selection and rate limit are unchanged.
- Coordinators and administrators can already download every official set from the admin report
  centre, so a watermarked on-screen copy exposes nothing new to them.

## Supersedes / Superseded by

Builds on ADR-071 (narrows it for report cards) and ADR-074.
