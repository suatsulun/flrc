# ADR-073: Dependabot groups per package manager and merges what passes

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-10-29  
**Phase:** 4.10 / operations

## Context

Dependabot opened one weekly pull request covering every package manager, and most failed.
The Python entry used the `pip` ecosystem, which reads `pyproject.toml` only; its lower bounds
already allowed every new release, so `uv.lock` never moved and each Python advisory needed a
manual lock update. Version updates touch direct dependencies only and security updates were
off, so an advisory in an indirect package failed the required locked-dependency audit on every
pull request. One breaking major version (Sentry 11) failed the whole group and held back every
safe update with it. The open group then went stale until main conflicted with it. A
multi-ecosystem group cannot move major versions to separate pull requests: Dependabot skips
dependencies outside the group in multi-ecosystem runs, so filtering majors would drop them.

## Decision

- The backend uses the `uv` ecosystem, so updates rewrite `uv.lock`.
- Each package manager has its own weekly group of minor and patch updates, on staggered days
  (npm Monday, uv Tuesday, Docker Wednesday, GitHub Actions Thursday). Docker groups every update
  because digest refreshes have no semver level. Major versions open as separate pull requests.
- The backend is on SQLAlchemy 2.1, and Dependabot ignores 2.2 and later. SQLAlchemy numbers its
  major series in the second digit, so semver calls a new series a minor update, but 2.1 dropped
  the default greenlet install and changed ORM autoflush, `filter_by`, `Row` typing and
  PostgreSQL named types. Moving to the next series is a deliberate migration.
- Dependabot security updates are enabled and grouped per package manager.
- The `dependabot merge` workflow takes the oldest eligible Dependabot pull request all the way
  in one run: it brings the pull request up to date, approves the `ci` and `security` runs that
  update leaves waiting, waits for them, squash-merges the pull request, deletes its branch,
  dispatches both workflows on main and starts a fresh run for the next pull request. Runs and
  pushes made with the workflow token trigger no other workflow, `workflow_run` included, so the
  run waits for its own checks instead of waiting to be triggered. Finished `ci` and `security`
  runs from people or Dependabot also start it, with a 15-minute schedule as a fallback, once the
  repository variable `DEPENDABOT_MERGE_ENABLED` is `true`. It skips pull requests whose verified
  Dependabot commit lists a major version, red ones and conflicting ones. It reads pull requests
  through the API and never runs their code.

## Alternatives considered

- Keep one multi-ecosystem pull request with major versions: fewest pull requests, but one
  breaking major keeps every routine update red until its code is fixed.
- One multi-ecosystem pull request without major versions: majors would never be proposed.
- Merge every update by hand: the pull requests went stale and conflicted with main.
- GitHub's native auto-merge from a `pull_request_target` workflow: tried first. Strict branch
  protection left every overtaken pull request behind, merges by the workflow token started no
  checks on main, and some merged branches stayed behind.

## Consequences

- Routine and security updates reach main without a person once CI is green, and each merge
  redeploys the public demo (ADR-064).
- One pull request merges at a time, so a burst of updates lands one check cycle apart.
- A branch update pushed with the workflow token leaves the pull request's `pull_request` runs
  waiting for approval, and branch protection counts only those runs; runs dispatched on the
  branch do not satisfy it. The workflow approves them once; the approved runs execute the same
  workflows Dependabot's own pushes run unapproved, on a commit that only merges main into
  Dependabot's branch. A run that stays waiting is left for a person with a warning.
- Merges made with the workflow token start no push runs, so the workflow dispatches `ci` and
  `security` on main, and both accept `workflow_dispatch`.
- Major versions and any group that contains one still need review.

## Supersedes / Superseded by

Extends ADR-043.
