# Workshop paper draft

**Recomputing the Verdict: What Replay Adds to Hash and Schema Checks on Records of AI-Assisted Go/No-Go Decisions**

Draft of 2026-11-21 for plan item P-037, revised on 2026-11-22. It has not been submitted anywhere and has not been peer reviewed. Whether and where to submit is the owner's decision ([decisions](../../.plan/decisions.md), proposed 2026-11-21).

**Owner action before any submission: the author block is incomplete.** The named build prints only the author's name. The AAAI kit expects affiliation and a complete address, including an email address, under the name. Set `\paperaffiliation` near the top of `paper.tex`; the anonymous build empties it.

The paper is four pages plus references and an appendix. It does not present the record format as new: signed, offline-verifiable receipts for agent decisions already exist, and some of their verifiers re-apply rules. It measures what recomputing the verdict from inputs kept in the record adds over a hash + JSON Schema check: on the conformance vectors, and on every single-leaf edit of the valid vectors, with digests left stale and with digests recomputed. It states that replay is a consistency check, what the records do not bind for an LLM agent, and where other work is ahead.

## Files

| File | Purpose |
| --- | --- |
| `paper.tex` | Source. Uses the AAAI-27 Author Kit when its two files are present, otherwise a plain two-column article with the same page geometry. |
| `paper-anonymous.tex` | Wrapper that builds the anonymized version from `paper.tex`. |
| `references.bib` | The cited entries only. Each was checked against its source page on 2026-11-21; the entries changed in the revision (revision 04 of the Farley draft, the MCP Tools page, the published versions of Tan et al. and South et al., the dates of the JSON Schema draft, the in-toto Statement specification) were checked on 2026-11-22. |
| `paper.pdf` | Named build made with the kit and tectonic 0.17.0. Rebuild it after any change to the source. |

## Build

The kit files are not redistributed here. Download the AAAI-27 Author Kit from <https://aaai.org/authorkit27/> and put `aaai2027.sty` and `aaai2027.bst` next to `paper.tex`; git ignores them.

```sh
cd docs/paper
mkdir -p build
tectonic --outdir build paper.tex              # build/paper.pdf
tectonic --outdir build paper-anonymous.tex    # build/paper-anonymous.pdf
cp build/paper.pdf paper.pdf
```

With pdfLaTeX, for example on Overleaf, upload the three source files and the two kit files, then:

```sh
pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper
```

For the anonymous PDF run the same four commands on `paper-anonymous`; on Overleaf, choose `paper-anonymous.tex` as the main document.

- Only tectonic builds were made. No pdfLaTeX build has been checked, and package versions differ, so re-check the page count on the PDF you submit.
- The main text has to end on page 4. In the tectonic build with the kit it ends 0.72 down the right column of page 4, and 0.78 in the anonymous build, because the kit prints a review notice on page 1. Without the kit files the fallback layout fills page 4 to its last line, so any added line needs a line cut. There, a cut before the "Lessons" heading can vanish into the stretched column above that heading; a cut after it counts.
- Keep the sources ASCII. With the kit's Type 1 fonts under tectonic, a typed dash or curly quote is dropped without an error.
- `paper.tex` contains three guarded shims for tectonic and a fallback preamble. pdfLaTeX skips the shims. Remove both blocks if a venue wants the kit preamble untouched.
- `\nocopyright` removes the AAAI copyright line in the named build, as AAAI asks for workshop papers. Delete that line for an AAAI Press publication.

## Open calls this format fits (checked 2026-11-21)

Dates are "anywhere on earth". Check each page again before relying on it.

| Call | Due | Length | Review | Proceedings |
| --- | --- | --- | --- | --- |
| [Loyal Agents workshop](https://loyalagents.github.io/aaai27/), AAAI-27 W27 | 2026-11-27 (extended from 2026-11-20) | up to 8 pages plus references; shorter papers welcome; appendix may follow the references | single-blind | non-archival |
| [Bench2Evidence bridge](https://bench-to-evidence.github.io/), AAAI-27 B2 | 2026-12-01 | short papers of 2 to 4 pages; whether references and an appendix count is not stated (re-checked 2026-11-22) | not stated | non-archival |

The Deployable AI workshop (DAI, AAAI-27 W12), which the plan named on 2026-11-07, closed on 2026-11-20 without an extension. Both open calls use the AAAI-27 Author Kit, submit through OpenReview and require an author to present in person in Montréal in February 2027.

## Before submitting

- **Author block.** See the owner action at the top of this page.
- **Results commit.** The evaluator that runs the baseline on every edited record (commit `b90ebc0`) and the results the paper reports (the commit after it) are not on main. Merge them before submitting. A squash merge leaves `b90ebc0` off main, so then regenerate the results on main, as `1522ec5` did for #311, and update together Appendices E and F, which name `b90ebc0`, and this page.
- **OpenReview.** Every author needs an active profile. The Loyal Agents page says a profile without an institutional email can take up to two weeks to be approved.
- **Use of AI tools.** Follow the venue's rule and add the statement it asks for. AAAI's publications policy says the use of an AI system in developing a publication "is only allowed if its role is properly documented in the manuscript"; the AAAI-27 call says authors "remain fully responsible for all submitted material".
- **Double-blind venues.** The anonymous build hides the author, the two URLs and the commit ids. The package names, command names, file paths and quoted program output (for example the message the chained example prints) still identify the repository.
- **Cited drafts.** The Internet-Drafts are works in progress and are revised often; the Farley draft moved to revision 04 on 2026-11-22 and is cited at 04. Re-check each draft's latest revision, and whether the arXiv preprints have since been published.
- **Appendix.** The main text points into the appendix seven times: Section 1 (Appendices C and F), Section 3 (Appendix D), Section 4 (Appendices A and B, Table 6) and the caption of Table 2 (Table 4). For a venue that allows no appendix, first reword or remove those seven references, then delete from the `\clearpage` after `\bibliography{references}` up to, not including, `\end{document}`. Deleting the appendix alone prints "??" in their place, and the build still succeeds.
- **Numbers.** If anything under `scripts/conformance/results/` changes, update the paper.

## Where the numbers come from

Appendix F of the paper names the file behind each statement. The results in `scripts/conformance/results/` name the commit they were generated from, `b90ebc0`, a commit of the branch that carries this revision, and record the git tree ids of the three packages and the evaluator. That commit is not on main, and a squash merge of this branch would keep it off; the tree ids survive the merge. The package tree ids equal those of `1626280` on main; only the evaluator changed, to run the baseline on every edited record. Every count the earlier results held is unchanged. In short:

| Numbers | Source |
| --- | --- |
| 185 vectors (56 valid, 64 tampered, 65 invalid); 36 of 64 tampered and 6 or 12 of 65 invalid vectors accepted by the baseline; 4,214 edits, 4,184 rejected stale, 3,466 resealed, 3,474 with OPA; exit codes; record sizes | [`scripts/conformance/results/RESULTS.md`](../../scripts/conformance/results/RESULTS.md) and `results.json` next to it |
| The baseline on the edited records: resealed, 1,104 rejected by the baseline, 2,375 (56.4%) only by the verifiers, 735 by neither, 13 only by the baseline; stale, 3,619 and 565; the split by exit code (2,263 mismatches and 112 input rejections that the baseline accepts) | `RESULTS.md`, section (c), "Hash + JSON Schema baseline on the edited records"; `results.json` at `/mutations/total/<mode>/baseline_strict` and `/mutations/by_type/<i>/<mode>/baseline_strict` |
| Per-package rows of the sweep table | Sums of the per-record-type rows of that file |
| The 748 passing edits by kind (333 inputs, 295 labels, 61 external-policy edits, 46 free text, 13 schema versions) | Our grouping of the per-field counts at `/mutations/by_type/<i>/resealed/undetected_field_counts`; Appendix B lists the grouping |
| What each tampered vector is | The `note` of the vector in `ai-workflows/*/conformance/manifest.json` |
| Canonical-form digests, replay tolerance, signing, exit codes | [`docs/DECISION_RECORDS.md`](../DECISION_RECORDS.md), [`SECURITY.md`](../../SECURITY.md) and [`.plan/decisions.md`](../../.plan/decisions.md) |
| Policy order, reviewer rules, external policy binding | `ai-workflows/decision-control/decisioncontrol/` (`policy.py`, `store.py`, `evidence.py`, `adapters/`) |

Eight statements rest on the code and a scratch run instead of a committed result, each about an edit the sweep does not make: an approval by a listed reviewer written into a pending record and re-hashed; a self-approval that also renames the proposer, re-hashed; an approval by an unlisted reviewer whose name is added to the frozen list, with both digests recomputed; a self-approval rewritten as schema 2; a frozen OPA `DENY` deleted and re-hashed; a schema 2 `HOLD` record with an extra first `"decision": "SHIP"`; a model name changed in both places of an answer record and re-hashed; and one `if`/`then` schema rule that rejects the lead example. Appendix B says so.

## What the paper does not claim

- No user, pilot, outside reproduction or outside contribution. The Node checker is a second implementation by the same author.
- No model or agent was run. Every answer, probability and proposal is a hand-written or synthetic fixture.
- The rates describe this corpus and single-leaf edits. They are not detection rates for records in general or against an adversary.
- No claim that a record that verifies was a right or an authorized decision. Replay is a consistency check: inputs and identities are what the producer supplied, whoever rewrites a record consistently passes, and an HMAC signature names no one.
- No compliance claim, and nothing beyond version 0.1.0 of the packages is released.
