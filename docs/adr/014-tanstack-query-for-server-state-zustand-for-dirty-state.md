# ADR-014: TanStack Query for server state, Zustand for dirty state

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 2.5

## Context

A grade grid has confirmed server values and unsaved human edits at the same time. Combining them into one state source causes confusion and save bugs.

## Decision

Use TanStack Query for server-confirmed data and Zustand for the dirty map of unsaved edits.

## Alternatives considered

- All state in React component state.
- All state in TanStack Query cache.
- Redux Toolkit.
- React Context.

## Consequences

- Clear mental model: Query owns what the server said; Zustand owns what the human typed.
- Save/leave guards become straightforward.
- The UI must merge cached and dirty values carefully when rendering cells.
