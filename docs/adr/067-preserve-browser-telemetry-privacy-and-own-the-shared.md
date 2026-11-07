# ADR-067: Preserve browser telemetry privacy and own the shared component stylesheet

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-10-14

**Phase:** 1.11 / security maintenance

## Context

The Sentry 11 dependency update removes `sendDefaultPii` and enables broader automatic data
collection by default. Both browser applications must retain the privacy posture in architecture
§8.6. Separately, the applications imported only `shadcn/tailwind.css` from the component-generator
package. Installing that CLI brought in a vulnerable `braces` dependency with no published fix
(GHSA-vfj7-8cjw-p6xm), even though the application never runs the generator.

## Decision

Both apps use shared Sentry options that explicitly disable automatic user data, cookies, HTTP
headers and bodies, URL query parameters, GraphQL and AI payloads, database and queue data, and
stack variables/context. Error reporting stays enabled when a DSN is supplied; tracing remains
disabled. A test loads each app's installed SDK, checks its resolved collection settings, and
captures a synthetic error through an in-memory transport, without contacting Sentry.

Keep the MIT-licensed stylesheet from shadcn 4.21.4 in `packages/ui/src/styles/shadcn.css`, beside
the owned component source. Both apps import it directly. Remove the unused generator package
instead of retaining its vulnerable dependency or suppressing the advisory. Preserve the upstream
copyright and license in the stylesheet; review upstream CSS changes explicitly when updating it.
Component generation remains a deliberate development action, not an application build step.

## Consequences

SDK upgrades cannot silently enable a new data-collection category without failing the privacy
test. Normal builds no longer install the generator and its server/network tooling. The stylesheet
is now maintained with the shared UI; dependency audit thresholds and required checks are unchanged.
