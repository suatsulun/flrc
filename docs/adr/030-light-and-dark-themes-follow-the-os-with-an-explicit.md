# ADR-030: Light and dark themes follow the OS, with an explicit override

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

A `.dark` block existed in both apps but held unmodified neutral-grey shadcn defaults, and nothing
ever added the `dark` class, so it was dead code that would have looked broken if enabled. Teachers
enter grades outside school hours and asked for a dark option.

## Decision

`resolveTheme` follows `prefers-color-scheme` unless the person pins a side; the resolved value is
stamped on `<html>` as `light`/`dark`. The control is a three-way segmented toggle
(light · system · dark) pinned to the bottom-left of the sidebar in both apps. The preference is
stored in `localStorage` under `flrc-theme`.

The pre-paint stamp is a **static file**, `public/theme-boot.js`, loaded blocking from `<head>`, not
an inline `<script>`: the apps ship `script-src 'self'` in `public/_headers`, which forbids inline
script. An inline snippet would have needed a CSP hash recomputed on every edit.

## Alternatives considered

- `next-themes`: it was already a `packages/ui` dependency, but it needs a provider and its own
  anti-flash script, for behaviour that is ~40 lines here. Dropped the dependency instead.
- Inline bootstrap plus a CSP hash: brittle, since every edit to the snippet silently breaks the
  page until `_headers` is updated.
- Media-query-only dark mode with no override: it cannot honour an explicit choice, which was the
  ask.

## Consequences

- No flash of the wrong theme, and no CSP exception.
- `public/theme-boot.js` duplicates the logic of `applyTheme`; both carry comments pointing at each
  other, and the storage key is the contract between them.
- Every screen now has to be checked in both themes.

## Supersedes / Superseded by

None.
