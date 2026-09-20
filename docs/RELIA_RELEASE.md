# RELIA local export and release identity

Develop RELIA in `projects/ai-decision-reliability-framework/`. The first standalone
candidate is exported to a local `relia-release` branch, with exactly the project tree
at its root. The intended annotated release tag is `relia/v<package-version>`.
The export command does not freeze the development checkout, accept a candidate,
create a tag, push, or publish. Rights review, reproduction, and release approval
remain separate steps in the project's release record.

## Prepare and export

Use Git and Python 3.9 or newer. Review and commit the complete candidate project
before exporting. Select that exact monorepo commit as `SOURCE_COMMIT`; the project's
index and working files must match it. Configure your existing `user.name` and
`user.email` in Git. Export commits use that identity and the actual current time.

From the monorepo root:

```bash
python3 scripts/export-relia.py \
  --source-ref SOURCE_COMMIT \
  --output /absolute/private/path/relia-candidate-0.1.5
```

Replace `SOURCE_COMMIT` and the output path with real values. The output's parent
must exist; the output directory itself must not exist and must be outside the
source repository. `--source-repo /absolute/path/to/ai-decision-system` can select
a different local checkout. The script defaults to its own containing repository.

The export refuses tracked changes, untracked files, and ignored files in the
project, except ignored `.venv/`, `.pytest_cache/`, `review-run/`, `repro-a/`,
`repro-b/`, `__pycache__/`, and `*.pyc` artifacts. It rejects committed symlinks and
submodules. Unrelated monorepo changes do not affect the export. Review the inventory
even when the command succeeds: identity checks do not establish rights or completeness.

The output contains:

```text
relia-candidate-0.1.5/
├── candidate/       # standalone Git repository; relia-release is its only branch
├── relia.bundle     # self-contained bundle of refs/heads/relia-release only
└── identity.json    # source/export mapping, bundle hash, and exact file inventory
```

The script transfers the project tree and its file objects, creates one root
commit, verifies a fresh clone of the bundle, and checks:

```text
SOURCE_COMMIT:projects/ai-decision-reliability-framework == EXPORT_COMMIT^{tree}
```

No monorepo parent commit or sibling project enters the export repository or bundle.
Tracked file bytes and modes are preserved, including files marked `export-ignore`.
The identity record remains outside the candidate so recording its commit identifier
does not change that commit. It includes SHA-256 for every exported file, including
the lock and stored result/manifest files when present. Retain the record with the
completed project [release record](../projects/ai-decision-reliability-framework/templates/release-record.md).

This implementation supports the first release only. It refuses locally known
`relia-release` branches (including remote-tracking refs) and `relia/v*` tags. It does
not contact the remote; confirm the actual remote release state before using it.
Subsequent release support must explicitly preserve the previous standalone release
as parent and validate that only standalone release history is reachable. Never
force-push a newly orphaned candidate over an existing release line.

## Reproduce and publish the accepted identity

Provide the bundle and independently recorded SHA-256, export commit, and tree
to the reviewer. Follow the full project
[reproduction protocol](../projects/ai-decision-reliability-framework/docs/REPRODUCE.md)
from the standalone clone's root. A local export or successful fixture test is not
a completed reproduction or release acceptance.

When the exact export has completed the required rights review, reproduction, and
maintainer acceptance, publish that same commit as `relia-release` and create its
annotated `relia/v<package-version>` tag. Do not recreate the export during publication.
Keep release refs outside normal feature-branch merge and cleanup flows and configure
the intended branch/tag protections before publication. If the monorepo integration
is rebased or squashed, record its final public commit separately and recheck project
tree equality. Record the annotated tag object and actual publication date, then
verify a fresh public clone returns the accepted export commit and tree.

After acceptance, publish consented review reports as release assets or later
development documentation; do not modify the accepted commit to add them.

## Export checks

Run the isolated fixture tests from the monorepo root:

```bash
python3 -m unittest discover -s scripts/tests -p 'test_export_relia.py' -v
```

These disposable tests check tree/file-mode preservation, bundle cloning, exclusion
of private parent objects, source immutability, and rejection of dirty candidates,
ignored source, existing output, symlinks, submodules, version mismatches, and existing
release refs. The synthetic identity in fixtures is test data only.
