# FL-ReportCard docs

This folder contains the project documentation I used while building FL-ReportCard.

## Files

| File                  | Purpose                                                                                       |
| --------------------- | --------------------------------------------------------------------------------------------- |
| `HANDBOOK.md`         | The complete step-by-step builder's manual. Follow this while coding.                         |
| `ARCHITECTURE.md`     | The deep-theory companion: system shape, domain model, security/KVKK, hosting, jobs, backups. |
| `DECISIONS.md`        | Architecture Decision Records. Update this when the project changes direction.                |
| `PRIVACY-DATA-MAP.md` | Every personal-data field, purpose, location, and processor.                                  |
| `SECURITY.md`         | Authentication boundary, production invariants, attack tests, and deployment proof.           |
| `RUNBOOK.md`          | Routine production operations and recovery links.                                             |
| `INCIDENT-RUNBOOK.md` | Incident triage, containment, communication, and recovery.                                    |
| `RESTORE-DRILLS.md`   | Recorded backup-restore exercises.                                                            |
| `TODO.md`             | The current release checklist; it must not point back to already completed handbook phases.   |

## Workflow

1. Open `HANDBOOK.md` and work on the next step.
2. Read `ARCHITECTURE.md` only when the handbook points to a deeper reason.
3. Update `DECISIONS.md` when you make or change a meaningful architecture decision.

Do not store real student data in any documentation file.
