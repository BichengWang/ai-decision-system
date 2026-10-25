# Repository tooling

Tools for the monorepo itself: standard-library Python, plus the pinned Node conformance checker. None of them is part of a
released package. Run them from the repository root. The component registry they
share is [`workspace.json`](../workspace.json); the `workspace-tooling` component
there routes changes under `scripts/` to the `Delivery policy` workflow.

The setup guide for the legacy `src/` research workbench is
[`src/README.md`](../src/README.md).

| Tool | Purpose | Documented in |
| --- | --- | --- |
| [`workspace.py`](workspace.py) | Lists components, finds the components and CI checks a change affects, runs component tests, validates the manifest, CI path filters, project layout, import boundaries and markdown links, and scaffolds a new standard-library project. Python 3.9+; `check` needs 3.10+ for the import-boundary rule | [ai-workflows README](../ai-workflows/README.md), [CONTRIBUTING](../CONTRIBUTING.md) |
| [`release.py`](release.py) | Inspects release candidates, validates a candidate or tag, extracts changelog notes, and dates a version's `Unreleased` entry. It never creates commits or tags. RELIA is out of scope. Python 3.11+ | [RELEASING](../docs/RELEASING.md) |
| [`pages.py`](pages.py) | Builds the GitHub Pages site from [`site/`](../site/index.html): serves every record schema at the path its `$id` names and mirrors the conformance vectors; [`pages.yml`](../.github/workflows/pages.yml) deploys it from `main`. Python 3.11+ | [DECISION_RECORDS](../docs/DECISION_RECORDS.md#schemas-and-conformance-vectors) |
| [`outreach.py`](outreach.py) | Checks the milestones in [`docs/launch/milestones.json`](../docs/launch/milestones.json) against PyPI (versions, yanks, trusted-publishing provenance) and GitHub Releases; for a reached milestone, re-runs its demo and opens one outreach tracking issue, and posts its GitHub Discussions announcement on request. Posts nothing outside the repository. Python 3.11+ and `gh` | [launch kit](../docs/launch/README.md#trigger) |
| [`continual_delivery.py`](continual_delivery.py) | Fail-closed GitHub queue snapshot, PR gate, review receipt and merge of a verified SHA for the local delivery task | [CONTINUAL_DELIVERY](../docs/CONTINUAL_DELIVERY.md) |
| [`publication_evidence.py`](publication_evidence.py) | Runs the existing project workflows and retains, or verifies, local publication evidence for the four-project scope. Makes no release, rights or impact claim. Python 3.11+ and `uv` | [PUBLICATION_GUIDE](../docs/portfolio/PUBLICATION_GUIDE.md) |
| [`export-relia.py`](export-relia.py) | Exports a committed RELIA candidate as a standalone repository, bundle and identity record. Does not publish, tag or accept a release. Python 3.9+ | [RELIA_RELEASE](../docs/RELIA_RELEASE.md) |
| [`conformance/`](conformance) | Node cross-check of every `ai-workflows/*/conformance/manifest.json`: validates declared documents against their JSON Schemas (Ajv, draft 2020-12) and recomputes every digest of every valid vector independently of Python. Pinned npm dependencies; Node 20+ | [DECISION_RECORDS](../docs/DECISION_RECORDS.md), [its README](conformance/README.md) |
| [`tests/`](tests) | Unit tests for the tools above, one file per tool | – |

Each tool prints its subcommands with `--help`.

## Makefile shortcuts

```sh
make workspace-list                      # components in workspace.json
make workspace-check                     # workspace.py tests and workspace.py check
make affected BASE=origin/main           # components and CI checks a change affects
make affected-test BASE=origin/main      # run the affected components' tests
make workspace-new NAME=<dir> SUMMARY="<one line>"
make release-status                      # release.py status
make relia-export RELIA_OUT=/abs/new/dir # export-relia.py; see RELIA_RELEASE
```

## Tests

```sh
python3 -m unittest discover -s scripts/tests -v
```

`make relia-export-test` runs only the export tests, and `make workspace-check`
runs only the workspace tests plus the manifest check.
