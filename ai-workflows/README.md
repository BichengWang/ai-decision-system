# Projects workspace

`projects/` is the monorepo boundary for independently buildable and releasable
projects. Each project owns its runtime metadata, lockfile, source, tests, and
project-specific documentation. Root tooling may provide convenience commands,
but a project must remain runnable from its own directory.

## Current project

| Project | Purpose | Run from |
| --- | --- | --- |
| [`ai-decision-reliability-framework`](ai-decision-reliability-framework/README.md) | Synthetic-data reliability evaluation and release controls | `projects/ai-decision-reliability-framework/` |

## Boundary rules

- Keep a project's directory name stable once it is used by release, export, or
  reproducibility records.
- Do not merge project dependencies into the root research environment merely
  for convenience. Projects may require incompatible Python or package versions.
- Put reusable, versioned code in a dedicated project rather than importing it
  ad hoc from another project's source tree.
- Keep the root `src/`, `data/`, and `docs/` tree as the legacy research
  workbench until a separately tested migration establishes new package
  boundaries.

## Adding a project

Create one directory per independently runnable project under `projects/`, give
it its own package metadata and tests, and add its entry to the table above.
Document any root convenience command alongside the project rather than making
the root environment a runtime requirement.
