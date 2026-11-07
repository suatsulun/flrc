# ADR-029: One shared design system in packages/ui, driven by semantic tokens

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

Both SPAs had duplicated their entire `index.css` (140 near-identical lines each), and the admin app
carried a block of `@layer components` rules that restyled bare `<form>`, `<table>`, and `<select>`
elements by descendant selector under `.admin-page`. Screens were assembled from one-off Tailwind
utility strings, so the same table appeared with four different paddings, and raw palette classes
(`bg-white`, `bg-slate-50`, `text-blue-700`) were sprinkled through the routes. `packages/ui`
existed but exported one placeholder component, so it was not actually the source of shared UI.

## Decision

Design tokens live once, in `packages/ui/src/styles/theme.css`, and each app's `index.css` is a
five-line import of it. Screens compose named primitives from `packages/ui`
(`AppShell`, `Card`, `Table`, `PageHeader`, `Badge`, `Stat`, `Field`, `NativeSelect`, `Segmented`,
`EmptyState`, `Skeleton`, `Kbd`) and consume semantic tokens (`bg-card`, `text-muted-foreground`,
`border-border`, `bg-warning-surface`) rather than raw palette values. The element-restyling
`.admin-page` CSS block is deleted.

The palette is a calm, cool blue: one accent (`--primary`, oklch(0.5 0.15 256)) dark enough to carry
white text at 4.5:1, muted status colours beside it, and near-white blue-cast surfaces so white
cards read as raised.

## Alternatives considered

- Keep per-app CSS and just recolour it: the duplication is what let the two apps drift in the
  first place, and recolouring does not fix inconsistent spacing.
- Adopt a third-party component library: the handbook already chose owned shadcn/ui source in
  `packages/ui`; replacing it would discard that decision for no new capability.
- Tokens as a TS object consumed in JS: Tailwind v4 reads `@theme`, so CSS is the native home and
  needs no build step.

## Consequences

- A colour or radius change lands in one file and both apps move together.
- New screens are assembled, not hand-styled, so they are consistent by default.
- `packages/ui` is now a real dependency of both apps, so a change there can break both; the
  monorepo `typecheck`/`lint` tasks cover this.
- `next-themes` was dropped (see ADR-030), removing one dependency.

## Supersedes / Superseded by

None.
