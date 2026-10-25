# Contributing

Pick a component before making a change. The [AI workflows workspace guide](ai-workflows/README.md)
describes project boundaries and available commands. Each project must run from
its own directory and must not import another project's package. Keep dependencies
and tests local to the component; `expgate`, `jevdecision`, and `decisioncontrol`
use only the Python standard library at runtime. The root `src/` tree is a research
workbench, not a shared runtime for those projects.

## Local checks

Use Python 3.11 or newer for workspace tooling and the three small projects.
Ensure `python3` resolves to that interpreter before running root make targets.
The one exception is expgate's dev-only reference generator (`tests/golden/generate.py`): its
`golden vectors` CI job runs on Python 3.10 because confseq 0.0.11 publishes wheels only up to 3.10.
From the repository root:

```sh
make workspace-check
make affected-test BASE=origin/main
```

Run the relevant component's tests from its own directory, on Python 3.11 and
3.13 when changing one of the three small projects:

```sh
# ai-workflows/experiment-gate/, jev-decision/, or decision-control/
python3 -m unittest discover -s tests -v

# ai-workflows/ai-decision-reliability/ (RELIA)
uv sync --frozen
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 uv run --frozen python -m pytest -q

# Repository tooling, from the root
python3 -m unittest discover -s scripts/tests -v
```

When changing a conformance manifest, vector or JSON Schema, also run the
independent Node check (Node 20 or newer; dependencies are pinned in a lockfile):

```sh
cd scripts/conformance && npm ci && node --test && node verify.mjs
```

For research workbench changes, follow the [baseline setup](src/README.md#baseline-check)
and run `make test` with Python 3.11. Additional component-specific checks are
documented in each project's README.

Commit notebooks without outputs or execution metadata: run `make notebooks` or
`python scripts/notebooks.py strip` before committing; the baseline checks this.

## Changes and review

Reproduce a bug with a failing test before fixing it. Test observable behavior,
including input boundaries, errors, invariants, and precedence. Every behavior
change must update that project's README and CHANGELOG. Describe the problem,
compatibility implications, exact verification commands, and results in the PR.

Use conventional-commit style subjects, as in the repository history:
`fix(validation): reject invalid input` or `docs(readme): clarify replay steps`.
Keep each change focused on the component it serves.

Be precise about evidence: synthetic or hand-written fixtures do not establish
live-model performance, calibration, adoption, or production use. Hashes detect
change; they do not prove authenticity or prevent forgery. State limitations and
unverified claims explicitly.

The maintainer cuts releases from per-component tags `<component>/vX.Y.Z`.
RELIA remains unreleased under its separate human-gated process. Contribution
does not authorize a release or publication.

Report vulnerabilities privately following [SECURITY.md](SECURITY.md).
Community participation is covered by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Releases

Maintainers follow [the package release guide](docs/RELEASING.md). RELIA uses its
separate human-gated release process linked there.
