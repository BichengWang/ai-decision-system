# Local continual delivery task

The recurring Codex task attached to this repository wakes every 30 minutes. It uses [PROJECT_PLAN.md](PROJECT_PLAN.md) as the initial cross-repository plan and GitHub issues labeled `continual-ready` as the shared execution queue. RELIA's roadmap and release record remain separate authorities. The task targets 15–20 merged PRs per America/Los_Angeles day, caps automatic merges at 20, and reports a shortfall without creating filler work.

## First-run prerequisites

1. Restore `gh auth login -h github.com` and verify `gh auth status` and `gh repo view` from this checkout. Keep credentials in the normal GitHub CLI store; do not place tokens in the repository or the scheduled prompt.
2. Confirm `main` branch protection requires `Delivery policy` and `RELIA required`, requires branches up to date, and applies to administrators. The controller queries these settings before any merge. Confirm the experiment-gate check names are `test (3.11)` and `test (3.13)` on a PR that changes that project, and `src baseline` from `Research baseline` on a PR that changes the research workbench.
3. Merge P-001 under the existing human process first. Pilot the new loop on P-002 and P-003, inspect their review receipts and CI results, and only then let the task pursue the full daily target. A schedule may run before these prerequisites, but it must report the blocker and make no merge.

The controller requires `src baseline` for PRs touching `src/`, root `tests/`,
`pyproject.toml`, `requirements.txt`, `setup.cfg`, `Makefile`, or
`.github/workflows/src-baseline.yml`, matching that workflow's path filters.
Missing, skipped, pending, failed, or wrongly attributed baseline checks block merging.

## Each wakeup

1. Run `python3 scripts/continual_delivery.py snapshot`. On an authentication or network failure, record the blocker and stop. Reconcile already open `continual-managed` PRs before selecting another issue; never have more than three open. One scheduled task owns this loop; overlapping invocations must resume the same issue and deterministic `automation/issue-<number>` branch rather than open another PR.
2. Sync `main`; do implementation in an isolated branch or worktree from its latest commit. Choose the oldest eligible `continual-ready` issue, unless a blocker or new evidence changes its priority. Link the issue, state its acceptance check, and add `Implementation run: <unique-run-id>` on its own line in the PR body. Before creating a branch, committing, or opening/updating a PR, check branch names, commit messages, PR title and description, and author/co-author attribution against the supplied `AGENTS.md` rule. Use the configured Git identity.
3. Run relevant local tests. Push only reviewed files and open a PR labeled `continual-managed`. A separate AI reviewer, with a fresh context and the exact PR head SHA, inspects the full diff, tests, and affected behavior. It writes a JSON report with `head_sha`, `verdict` (`PASS` or `BLOCK`), `blocking_findings`, `reviewer_run` distinct from the implementation run, and a concise `summary`. Record that report with `python3 scripts/continual_delivery.py record-review <PR> <report.json>` using the repository owner's authenticated account. A new push requires a new review. Only owner-authored receipts count, and a BLOCK on the same SHA cannot be overridden by a later PASS. The receipt records process separation; with one GitHub account it cannot cryptographically prove separate authorship, so preserve the review task transcript for audit.
4. Run `python3 scripts/continual_delivery.py gate <PR>`. Resolve every blocker and rerun review and CI when the head changes. Only `python3 scripts/continual_delivery.py merge <PR>` may merge a managed PR. It checks the exact SHA again, invokes GitHub's SHA-conditional squash merge, and confirms the merge commit is on `main`. Run the relevant post-merge smoke check, then close the linked issue and record the outcome.
5. At the end of the Los Angeles day, report merged count, review blocks, failed checks, reversions, median time to merge, and any shortfall or blocker. Use that evidence to update the queue or propose process changes through the same review gate. Never relax required checks to increase throughput.

## Boundaries and recovery

- Standalone releases, `relia-release`, tags, and publication never enter this loop. Release-control files listed in the controller are also excluded from automatic merging. Use [RELIA_RELEASE.md](RELIA_RELEASE.md) and its rights, reproduction, and maintainer acceptance records for publication.
- The old `auto-merge` label has no merge authority. The GitHub workflow only removes merged branches, and the old root README alias was removed.
- The controller fails closed on absent authentication, unavailable GitHub, missing branch protection, skipped or failed checks, stale review, draft or conflicting PRs, prohibited attribution, or the daily cap. Keep blocked PRs open for repair; do not retry by bypassing the controller.
- GitHub PRs and issues are the durable execution state. If the Mac sleeps or a run is interrupted, the next wakeup re-reads remote state and continues. The local schedule cannot meet a daily throughput target while the Mac is off.
