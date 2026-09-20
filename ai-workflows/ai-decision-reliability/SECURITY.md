# Security

Before any public push of this project or publication of a standalone release, verify that
its exact staged file set contains
only synthetic data and no credentials or secrets. Review the complete file inventory, run
a credential/secret scan, and record the method and result in the completed sidecar copy of
`templates/release-record.md`. This required release condition is not a representation about
the surrounding working repository or any unreviewed parent directory.

Development is planned in the public `BichengWang/ai-decision-system` monorepo; pushing a
feature branch there also discloses its content. A project-only release branch limits the
release artifact's contents but does not hide the monorepo or its history. Review the source
project inventory and the exported root tree separately and record their equality.

Report a suspected vulnerability or an accidental inclusion of non-synthetic data privately
to the maintainer through the repository's private security-advisory feature if enabled.
Do not put credentials, private data, or confidential rights records into a public issue.
