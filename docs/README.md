# FL-ReportCard documentation

Updated against the local repository on 2026-09-11. The handbook retains the build sequence;
current status lives in the release checklist. A documentation update is not deployment proof.

| File                                       | Purpose                                                                    |
| ------------------------------------------ | -------------------------------------------------------------------------- |
| [HANDBOOK.md](HANDBOOK.md)                 | Learning sequence and step checks, with current implementation amendments. |
| [ARCHITECTURE.md](ARCHITECTURE.md)         | Domain model, state ownership, security, reports, and hosting boundaries.  |
| [DECISIONS.md](DECISIONS.md)               | ADR history and explicit supersessions.                                    |
| [TODO.md](TODO.md)                         | Implemented scope, pending changes, and open release gates.                |
| [AI-HANDOFF.md](AI-HANDOFF.md)             | Ready-to-copy prompt for another AI to review the repository first.        |
| [PRIVACY-DATA-MAP.md](PRIVACY-DATA-MAP.md) | Stored personal data, processors, purposes, and retention ownership.       |
| [SECURITY.md](SECURITY.md)                 | Current access controls, tests, and deployment checks.                     |
| [SECURITY-AUDIT.md](SECURITY-AUDIT.md)     | Dated audit findings and source-level follow-up status.                    |
| [RUNBOOK.md](RUNBOOK.md)                   | Launch, routine operations, and rollback.                                  |
| [INCIDENT-RUNBOOK.md](INCIDENT-RUNBOOK.md) | Containment and recovery; school owners authorize communication.           |
| [RESTORE-DRILLS.md](RESTORE-DRILLS.md)     | Human restore procedure and actual drill evidence.                         |
| [SELF-HOSTING.md](SELF-HOSTING.md)         | School server setup and operation using published images.                  |
| [RELEASING.md](RELEASING.md)               | Version tags, image publishing, and deployment pins.                       |
| [UPGRADING-1.2.0.md](UPGRADING-1.2.0.md)   | Historical 1.2.0 upgrade notes, separated from subsequent source changes.  |

Start with [AGENTS.md](../AGENTS.md) for AI behavior, then the relevant handbook step.
Read the architecture document for the reasoning and the ADRs for documented changes. Existing
code and manifests establish what is present; report mismatches instead of silently overriding
project rules.

App-specific entry points: [teacher](../apps/teacher/README.md), [admin](../apps/admin/README.md),
[backend](../apps/backend/README.md), [branding](../branding/README.md), and
[infrastructure](../infra/README.md). Keep real student data and private report assets out of docs.
