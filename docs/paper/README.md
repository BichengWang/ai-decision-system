# Workshop paper draft

**Recomputing the Verdict: What Replay Adds to Hash and Schema Checks on Records of AI-Assisted Go/No-Go Decisions**

Draft of 2026-11-21 for plan item P-037. It has not been submitted anywhere and has not been peer reviewed. Whether and where to submit is the owner's decision ([decisions](../../.plan/decisions.md), proposed 2026-11-21).

The paper is four pages plus references and an appendix. It does not present the record format as new: signed, offline-verifiable receipts for agent decisions already exist. It studies what the verifiers here add, which is recomputing the verdict from inputs kept in the record, and it measures that against a hash + JSON Schema check on the conformance vectors. It states what the records do not bind for an LLM agent and where other work is ahead.

## Files

| File | Purpose |
| --- | --- |
| `paper.tex` | Source. Uses the AAAI-27 Author Kit when its two files are present, otherwise a plain two-column article with the same page geometry. |
| `paper-anonymous.tex` | Wrapper that builds the anonymized version from `paper.tex`. |
| `references.bib` | The cited entries only. Each was checked against its source page on 2026-11-21. |
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

- Only tectonic builds were made. No pdfLaTeX build has been checked, and package versions differ, so re-check the page count on the PDF you submit.
- The main text has to end on page 4. In the tectonic build it ends about two thirds down the right column of page 4. The anonymous build is tighter, because the kit prints a review notice on page 1.
- Keep the sources ASCII. With the kit's Type 1 fonts under tectonic, a typed dash or curly quote is dropped without an error.
- `paper.tex` contains three guarded shims for tectonic and a fallback preamble. pdfLaTeX skips the shims. Remove both blocks if a venue wants the kit preamble untouched.
- `\nocopyright` removes the AAAI copyright line in the named build, as AAAI asks for workshop papers. Delete that line for an AAAI Press publication.

## Open calls this format fits (checked 2026-11-21)

Dates are "anywhere on earth". Check each page again before relying on it.

| Call | Due | Length | Review | Proceedings |
| --- | --- | --- | --- | --- |
| [Loyal Agents workshop](https://loyalagents.github.io/aaai27/), AAAI-27 W27 | 2026-11-27 (extended from 2026-11-20) | up to 8 pages plus references; shorter papers welcome; appendix may follow the references | single-blind | non-archival |
| [Bench2Evidence bridge](https://bench-to-evidence.github.io/), AAAI-27 B2 | 2026-12-01 | short papers of 2 to 4 pages | not stated | non-archival |

The Deployable AI workshop (DAI, AAAI-27 W12), which the plan named on 2026-11-07, closed on 2026-11-20 without an extension. Both open calls use the AAAI-27 Author Kit, submit through OpenReview and require an author to present in person in Montréal in February 2027.

## Before submitting

- **Author block.** Affiliation and contact are empty. Set `\paperaffiliation` near the top of `paper.tex`.
- **OpenReview.** Every author needs an active profile. The Loyal Agents page says a profile without an institutional email can take up to two weeks to be approved.
- **Use of AI tools.** Follow the venue's rule and add the statement it asks for. AAAI's publications policy says the use of an AI system in developing a publication "is only allowed if its role is properly documented in the manuscript"; the AAAI-27 call says authors "remain fully responsible for all submitted material".
- **Double-blind venues.** The anonymous build hides the author, the two URLs and the commit ids. The package names, command names and file paths still identify the repository.
- **Cited drafts.** The Internet-Drafts are works in progress and are revised often. Re-check their revisions and the three papers marked "to appear".
- **Appendix.** Delete everything after `\bibliography{references}` for a venue that allows no appendix.
- **Numbers.** If anything under `scripts/conformance/results/` changes, update the paper.

## Where the numbers come from

Appendix F of the paper names the committed file behind each statement. In short:

| Numbers | Source |
| --- | --- |
| 185 vectors (56 valid, 64 tampered, 65 invalid); 36 of 64 tampered and 6 or 12 of 65 invalid vectors accepted by the baseline; 4,214 edits, 4,184 detected stale, 3,466 resealed, 3,474 with OPA; exit codes; record sizes | [`scripts/conformance/results/RESULTS.md`](../../scripts/conformance/results/RESULTS.md) and `results.json` next to it, generated from commit `1626280` |
| Per-package rows of the sweep table | Sums of the per-record-type rows of that file |
| What each tampered vector is | The `note` of the vector in `ai-workflows/*/conformance/manifest.json` |
| Canonical-form digests, replay tolerance, signing, exit codes | [`docs/DECISION_RECORDS.md`](../DECISION_RECORDS.md) and [`.plan/decisions.md`](../../.plan/decisions.md) |
| Policy order, reviewer rules, external policy binding | `ai-workflows/decision-control/decisioncontrol/` (`policy.py`, `store.py`, `evidence.py`, `adapters/`) |

Two statements rest on the code and a scratch run instead of a committed result: a record rewritten as schema 2 replays with the proposer as reviewer, and a model name changed in both places of an answer record passes its verifier. Appendix B says so.

## What the paper does not claim

- No user, pilot, outside reproduction or outside contribution. The Node checker is a second implementation by the same author.
- No model or agent was run. Every answer, probability and proposal is a hand-written or synthetic fixture.
- The rates describe this corpus and single-leaf edits. They are not detection rates for records in general or against an adversary.
- No compliance claim, and nothing beyond version 0.1.0 of the packages is released.
