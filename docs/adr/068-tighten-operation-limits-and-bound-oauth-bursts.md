# ADR-068: Tighten operation limits and bound OAuth bursts

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-10-14

**Phase:** 4.8 / security hardening

## Context

The previous OAuth allowance permitted 120 requests in five minutes without a shorter burst
limit. Expensive operations shared a default of ten requests per minute. Lower limits must still
allow multiple teachers to sign in through one public address and administrators to page through
an import review.

## Decision

Require both 30 requests per minute and 60 per five minutes for each OAuth endpoint and client
address. Login and callback retain independent counters. Limit each account to five report
requests, three audit CSV exports, three workbook commits, and thirty workbook previews per
minute, with independent operation counters. Ordinary grade saves are unchanged.

Keep atomic Redis counters, pseudonymized identities, `Retry-After`, and school-mode failure
closure. Test the real Redis script under concurrent requests, each policy boundary, separate
identities and operations, expiry, and loss of Redis. Import review must not spend the commit
allowance.

## Consequences

Repeated expensive work and rapid OAuth traffic are rejected earlier. A shared address can
complete at most thirty sign-ins per minute and sixty per five minutes; users exceeding a budget
must wait for the indicated reset. These remain fixed-window controls on selected endpoints,
not a general API limiter or upstream DDoS protection.
