# Repository delivery plan

This is the cross-repository work queue. RELIA's own [roadmap](../ai-workflows/ai-decision-reliability/docs/ROADMAP.md) remains authoritative for its research and release milestones. The scheduled delivery task turns the ready entries below into GitHub issues carrying the stable `Plan ID`, `continual-ready` label, concrete outcome, and acceptance check. It searches existing issues and PRs for that ID before creating anything, so interrupted runs do not duplicate work. An issue is closed only after its PR is verified on `main` and its acceptance check passes.

| Priority | Plan ID | Outcome | Acceptance check |
| --- | --- | --- | --- |
| 1 | P-001 | Replace label-triggered merging with an exact-head, independently reviewed gate and establish the recurring controller. | Controller regression tests pass; a stale review, missing CI, merge conflict, release path, and daily cap all block merging; GitHub branch rules are verified before the pilot. |
| 2 | P-002 | Repair stale repository links and commands left by the project move to `ai-workflows/`. | Every local Markdown link in the root and workspace readmes resolves; documented commands reference existing paths and targets. |
| 3 | P-003 | Give the legacy `src/` workbench a runnable, bounded baseline check. | A clean checkout can run the documented command and a PR touching that area receives a relevant CI check; known external-service tests are isolated. |
| 4 | P-004 | Improve experiment-gate failure coverage without altering its decision thresholds. | Boundary and malformed-input cases are covered; both Python versions in its CI pass. |
| 5 | P-005 | Select the next non-release RELIA implementation item from its roadmap and limitations. | The change cites the exact roadmap item, retains adverse results, and passes RELIA's project suite. Publication remains under its separate release process. |

After each merge, reprioritize using review findings, CI failures, regressions, and the project's own roadmap. Add a new item only when it has an observable outcome and acceptance check. Do not subdivide work solely to reach the daily PR target.
