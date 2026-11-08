# ADR-050: Keep screen logic focused and confirm the values actually submitted

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-08

**Phase:** 2-3, maintenance

## Context

The teacher grid and admin class page had accumulated cell rendering, form state, database
operations, dragging, navigation, and repeated UI configuration in single large files. The grade
save callback also read the live draft after the request completed. This could show an old grade
after clearing it, or silently lose an edit made while the request was pending.

## Decision

Keep the existing applications, libraries, database model, public API, and screens. Extract the
teacher's cell and table rendering into the existing grid folder. Let the admin's teacher,
column, and roster components own their corresponding forms and mutations. Keep the table and
column forms mounted when switching to the removal panel so unfinished form values survive.

Share the duplicated shell/academic labels, sibling-tab prefetch loop, and admin cache
invalidation. Use SQLAlchemy's direct scalar-query API instead of wrapping execute results, and
keep one implementation of writable-class validation and grant renewal. Column dragging and
arrow controls now use the same reorder operation, including inactive columns in its scope.

Save responses update the query cache from a snapshot of the submitted cells, including explicit
nulls. Only applied cells are acknowledged. Newer edits remain in Zustand and use the returned
versions for their next save. A draft generation counter prevents late responses from restoring
changes after the user discards or leaves a grid. Conflict overwrite, ownership confirmation,
and the server's audit/undo rules remain in place.

## Consequences

The two main route files become much smaller, and each editor can be understood independently.
Explicit component props and save regression coverage add some code; this change prioritizes
simpler responsibilities and removes repeated logic rather than compressing business rules.
No dependency, migration, generated-client change, or feature removal is required.
