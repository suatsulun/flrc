# ADR-072: Fields are named in their subject's language

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-10-22  
**Phase:** 2.x (grid and columns) maintenance

## Context

Column labels are stored per language (§4.10). The teacher grid picked the label matching the UI
language, while the admin class tables always showed the Turkish label, so an English UI showed
"Gelişim Sınavı 1" and a German teacher's fields changed name whenever the UI language changed.
Admin "Add column" stored only a Turkish label, whatever the subject.

## Decision

- Every field has one name in the apps: English fields in English, German fields in German,
  French fields in French. The UI language never changes it. The teacher grid, admin tables,
  conflicts, archive, audit and exports all use it; the grid and archive drop their `locale`
  parameter.
- Creating a column takes a single `name` (and optional `group`), stored under the subject's
  language. The API no longer accepts per-language labels.
- Fields that a printed card shows in Turkish also need their Turkish wording (`turkish_name`,
  plus `turkish_group` when grouped), or the API answers `turkish_wording_required`. That is
  every primary English field (grades Hazırlık–4) and every German/French rating row and teacher
  note. German/French scores only feed the karne average and middle-school English fields print
  in English alone, so they need none. The admin forms show the Turkish box only when needed.
- Names cannot be edited after creation, so the same rule guards the other ways a field reaches
  a card: changing an unused field's type answers `turkish_wording_required` when the new type
  prints Turkish wording the field lacks (recreate it instead), and copying a column set checks
  every copied field against the target first. A copy into the other karne language answers
  `copy_language_mismatch` unless the fields already carry names in that language; nothing is
  copied when a field fails either check.
- Stored labels without the subject's language fall back to Turkish, then any entry, so
  existing columns stay readable.
- Printed cards are unchanged: they stay bilingual, Turkish first with the subject's language
  beneath, from the stored wording.

## Alternatives considered

- Follow the UI language everywhere: one field gets several names, and teachers no longer
  recognise the names printed on the school's cards.
- Collapse labels to a single stored string: loses the Turkish wording the bilingual karne
  prints for the school's checklist rows.

## Consequences

Columns created through the old Turkish-only form keep their Turkish name until they are
recreated. Admins type one name plus, for bilingual cards, its Turkish wording instead of four
translations.

## Supersedes / Superseded by

Narrows §4.10 for field names; printed report labels keep the per-language rules. ADR-076
supersedes the "Names cannot be edited after creation" bullet: the subject-language name is now
editable.
