# Pause and rollback procedure

1. **Trigger:** any failed release gate, SEV1 signal, or unexplained material regression.
2. **Pause** the affected version (stop serving it in the controlled environment).
3. **Revert** to the most recent release whose release record shows all gates passed; verify the artifact hash against that record.
4. **Verify:** re-run `python -m relia.run` and, when applicable, any deployment-specific smoke/canary test on the reverted version; compare hashes and gate report with the release record.
5. **Record** the rollback in an incident record, including time to contain and time to restore.
6. **Restore** traffic only after the reviewer signs the record.
7. **Drill** this procedure for each release after a prior accepted rollback target exists. For the initial release, test pause/rejection and artifact-identity verification because there is no prior accepted release to restore.

For a local artifact-level drill without a deployed service, “pause” means marking the
candidate unavailable for release, “revert” means checking out the last accepted tagged
artifact, and “restore” means verifying its recorded hash and rerunning its gate report.
Record elapsed steps, but do not describe such a drill as production recovery.
