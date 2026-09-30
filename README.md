# Scalable AI Decision Systems

Research and experiment workspace for **AI-assisted decision making**: multi-agent reasoning, reinforcement learning, causal inference, and quantitative finance.

## Projects

Run the commands below from the repository root. The [workspace guide](ai-workflows/README.md) lists the independent projects and their own run directories.

| Project | Scope | Status and environment |
| --- | --- | --- |
| [RELIA](ai-workflows/ai-decision-reliability/README.md) | Reproducible evaluation and release controls for synthetic commerce offers and ranking | Unreleased candidate; independent Python environment and lockfile |
| [Experiment gate](ai-workflows/experiment-gate/README.md) | Ship / hold / rollback decisions for online A/B tests of decision models | Standard library only; no lockfile |
| Existing `src/` research | Agents, RL, ML, finance, and study material | Research and experiments using the root environment |

RELIA's [specification](ai-workflows/ai-decision-reliability/docs/SPEC.md),
[reproduction protocol](ai-workflows/ai-decision-reliability/docs/REPRODUCE.md),
and [limitations](ai-workflows/ai-decision-reliability/docs/LIMITATIONS.md)
define its bounded scope. Other projects are not validated RELIA integrations.
Its development and release dates are recorded independently of this repository's history.

```shell
make relia-sync
make relia-test
make relia-reproduce RELIA_OUT=/absolute/new/run-directory
```

These commands use only the project's own environment. See the
[release workflow](docs/RELIA_RELEASE.md) for project-only snapshots and their
source identity. No accepted RELIA public release is claimed yet.

The root MIT license applies to the existing research material it covers. RELIA
has a separate [licensing status](ai-workflows/ai-decision-reliability/LICENSE)
and currently grants no license; its intended Apache-2.0 release remains subject
to rights clearance.

Setup, environments, the directory layout and the decision-loop quick start for the
`src/` research material are in the [setup guide](scripts/README.md).
