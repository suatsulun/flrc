# ADR-042: Pending work is visible and class tabs are warmed

[ADR index](README.md)

**Status:** Accepted; the loading-state sentence of the decision is superseded by ADR-081

**Date:** 2026-08-21
**Phase:** 2.x-4.x

## Context

Year activation, audit export, workbook import, PDF rendering, and cold class-table requests can
take long enough to look like a missed click. Pending states were inconsistent, the admin toast
renderer was easy to miss, and native browser confirmation prompts did not match the application.

## Decision

The shared button owns one `pending` contract: preserve its layout, disable repeated activation,
overlay a spinner, expose `aria-busy`, and keep an accessible pending label. ~~Both app shells show a
first-query activity indicator; important page entry states use stable skeletons.~~ (Superseded by
ADR-081: layout-shaped skeletons everywhere, a visually hidden status.) Mutations always
surface errors globally, while meaningful saves, transitions, exports, and background job state
changes use localized success/loading/error toasts.

Typed confirmations use the shared site dialog. TanStack Router's resolver dialog handles internal
navigation away from dirty grades; the browser's mandatory `beforeunload` warning remains only for
closing or leaving the document itself.

Direct PDF actions open a user-initiated generating tab, fetch authenticated PDF bytes, replace the
tab with a blob URL when ready, and restore the initiating button. Admin and teacher class views
prefetch only the sibling tabs in the selected grade, after a short delay and on hover/focus, with a
30-second freshness window. Background warming is sequential per browser; hover and keyboard focus
still prioritize the class a user is about to open.

## Consequences

- Slow actions cannot be submitted twice and never look inert.
- Success, failure, and background completion are visible without browser alert boxes.
- Switching among A-G class tabs normally reads from the warm query cache.
- One selected grade can make several small speculative roster/grid reads; the bound prevents a
  whole-school prefetch storm, and sequential warming limits roughly twenty concurrent users to
  roughly twenty speculative reads at once.
