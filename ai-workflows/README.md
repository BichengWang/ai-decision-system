# AI workflows workspace

`ai-workflows/` is the monorepo boundary for independently buildable and
releasable projects. Each project owns its runtime metadata, lockfile, source,
tests, and project-specific documentation. Root tooling may provide convenience
commands, but a project must remain runnable from its own directory.

## Current projects

| Project | Purpose | Run from |
| --- | --- | --- |
| [`ai-decision-reliability`](ai-decision-reliability/README.md) | Synthetic-data reliability evaluation and release controls (RELIA) | `ai-workflows/ai-decision-reliability/` |
| [`experiment-gate`](experiment-gate/README.md) | Ship / hold / rollback decisions for online A/B tests of decision models, with guardrails and sample-ratio checks | `ai-workflows/experiment-gate/` |
| [`jev-decision`](jev-decision/README.md) | Jev as the core decision model: typed yes/no, choice, and score decisions, with the OpenAI Decisions API as an alternative backend, and offline evaluation against labeled cases | `ai-workflows/jev-decision/` |

From the repository root, use the convenience targets in the [root Makefile](../Makefile):

```bash
make relia-sync        # uv sync --frozen in the project directory
make relia-test        # run the project test suite single-threaded
make relia-reproduce RELIA_OUT=/abs/new/dir
make expgate-test       # experiment-gate unit tests (standard library only)
make expgate-run EXPGATE_OUT=/abs/new/dir
make jev-test          # jev-decision unit tests (standard library only)
make jev-dry-run       # print the example request for both backends
make jev-eval          # evaluate the example cases from recorded responses
```

## Workspace manifest

[`workspace.json`](../workspace.json) at the repository root registers every
component of the monorepo: the projects above, the legacy `src/` research
workbench, and the repository tooling in `scripts/`. For each component it
records:

| Field | Meaning |
| --- | --- |
| `kind`, `path` | `project` (directly under `ai-workflows/`), `legacy`, or `tooling`, and the component's directory |
| `sources`, `packages` | The Python files the component owns and the top-level import names it provides |
| `third_party_imports` | Import names allowed besides the standard library and its own packages (`null` leaves them unchecked) |
| `paths` | Changed paths that affect the component, in GitHub path-filter syntax (`*`, trailing `/**`) |
| `ci`, `checks` | The workflow that validates it, how that workflow is triggered, and the check names the delivery gate requires |
| `test`, `test_env` | Commands run from the component directory (or `cwd`), and environment defaults for them |

A change to `workspace.json` itself affects every component.
[`scripts/workspace.py`](../scripts/workspace.py) reads the manifest; it uses
only the standard library:

```bash
make workspace-list                       # components, paths, and CI checks
make affected                             # components and checks your branch affects (BASE=origin/main)
make affected-test                        # run the tests of the affected components
make workspace-test COMPONENTS="experiment-gate workspace-tooling"
make workspace-check                      # tool tests plus the consistency check below
make workspace-new NAME=<name> SUMMARY="<one line>"   # scaffold a project (see below)
```

`python3 scripts/workspace.py --help` lists the underlying commands. Test
commands that start with `python3` run under the interpreter that runs the tool,
so `python3.11 scripts/workspace.py test experiment-gate` tests on Python 3.11.

The required `Delivery policy` check runs `scripts/workspace.py check`. It reads
tracked files plus untracked files that are not ignored, so it also covers work
you have not committed yet. It fails when:

- a directory under `ai-workflows/` is not registered, or a project lacks a
  `README.md`, `pyproject.toml`, or `tests/`, or is not linked from the root and
  workspace readmes;
- a workflow's path filters differ from its component's `paths` plus
  `workspace.json`, a check is attributed to a workflow with another name, or no
  job in the workflow reports a declared check name (a job's `name`, or its id,
  expanded over a single-key matrix as GitHub names matrix jobs);
- a Python file belongs to no component or to several;
- a component imports another component's package, or a project imports a
  third-party module it does not declare;
- a local Markdown link in the root or `docs/` pages, or in a project or
  tooling component, points to a missing file or to a heading that does not
  exist (links inside code, external URLs, and the legacy `src/` notes are not
  checked).

The [delivery controller](../scripts/continual_delivery.py) derives the checks a
pull request must pass from the same manifest, and RELIA CI asks
`scripts/workspace.py github-changes --component relia` whether a change needs
its full validation.

## Boundary rules

- Keep a project's directory name stable once it is used by release, export, or
  reproducibility records.
- Do not merge project dependencies into the root research environment merely
  for convenience. Projects may require incompatible Python or package versions.
- Put reusable, versioned code in a dedicated project rather than importing it
  ad hoc from another project's source tree. `workspace.py check` enforces this
  for registered packages.
- Keep the root `src/`, `data/`, and `docs/` tree as the legacy research
  workbench until a separately tested migration establishes new package
  boundaries.

## Adding a project

From the repository root:

```bash
make workspace-new NAME=<name> SUMMARY="<one-line description>"
# or: python3 scripts/workspace.py new <name> --summary "..." [--package <import_name>] [--dry-run]
make workspace-check
make workspace-test COMPONENTS=<name>
```

`new` creates a standard-library project in `ai-workflows/<name>/` (`README.md`,
`pyproject.toml`, `.gitignore`, the package, and a first test), a
`.github/workflows/<name>-ci.yml` workflow that runs the tests on Python 3.11 and
3.13 with the action versions the other workflows pin, the project's
`workspace.json` entry, and its rows in the table above and in the root
[README](../README.md). It checks every input before writing and refuses existing
paths, so the result passes `make workspace-check` as generated. The delivery gate
then requires `<name> (3.11)` and `<name> (3.13)` for changes to the project.

When a project needs third-party packages, list their import names under its
`third_party_imports`, add a lockfile, and adjust its workflow. For a project set up
by hand, register it with `ai-workflows/<name>/**` in both `sources` and `paths`,
give its workflow path filters exactly those `paths` plus `workspace.json`, and
list each job's check name under `checks`.

Document any root convenience command alongside the project rather than making
the root environment a runtime requirement.
