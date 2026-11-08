# ADR-046: Parallel class rendering with ordered PDF assembly

[ADR index](README.md)

**Status:** Partially superseded by ADR-080 (a process per document, no warm pool); extended by ADR-077 (report jobs)

**Date:** 2026-09-04
**Phase:** 4.2-4.4 maintenance

## Context

Profiling a synthetic 30-student middle-school class showed that Jinja rendering took about four
milliseconds while WeasyPrint layout and painting took 2.71 seconds. Four 30-student classes took
13.75 seconds in one document. Table layout, page layout, and PDF painting dominated the profile;
template compilation, branding assets, and DTO assembly did not. Reused font and image caches did
not reliably improve the workload, and threads made it slower.

Every class is already an independent print boundary. A middle-school class starts its own A5
guillotine stack, and elementary/second-language cards are independent duplex sheets. This permits
parallel work without changing a card's HTML or CSS.

## Decision

Keep the synchronous authenticated PDF endpoint from ADR-028. For a report set of at least twelve
already-imposed sheets, split that ordered sheet list into balanced contiguous chunks, render the
chunks in a lazy warm process pool bounded to four CPU-visible workers, then use pypdf to assemble
the results in their original order. Smaller reports stay on the existing direct WeasyPrint path.
Preserve the first document's PDF metadata during assembly.

pypdf becomes a runtime dependency. Celery remains reserved for durable year exports; report cards
are not moved back into job payloads or temporary artifact storage.

## Alternatives considered

- Reuse a WeasyPrint font configuration or image cache: measured as neutral or slower here.
- Render classes in threads: slower because the dominant layout work did not scale across threads.
- Change the score tables to fixed layout: potentially faster, but it changes the deliberate
  content-sized columns and therefore violates print-layout compatibility.
- Cache completed class PDFs: rejected because invalidation after grade, roster, column, locale, or
  branding changes would enlarge the stale-report risk.

## Consequences

- Multi-class PDF latency falls substantially on hosts with more than one available CPU.
- Page content, size, order, and per-class guillotine imposition remain unchanged and are regression
  tested against the original single-document renderer.
- Each API process may keep up to four renderer child processes warm after its first multi-class
  request, trading memory for lower subsequent latency.

## Supersedes / Superseded by

Extends ADR-028; the endpoint and the four school-wide report-set contract are unchanged.
ADR-080 replaces the warm pool: a parallel download renders each document in a process of its
own, stopped before the render returns.
