# Reproducible controls for bounded AI-assisted decisions

**Author-produced technical portfolio report — prepared 2026-10-11**  
Repository maintainer: Bicheng (Kenneth) Wang. Prepared with AI-assisted engineering and source research. This is not peer-reviewed research, independent recognition, an accepted package release, attorney advice, or a determination of EB-2 NIW eligibility.

## 1. Findings and scope

Four independent Python projects demonstrate distinct controls around AI-assisted decisions: synthetic commerce evaluation, online-experiment decision logic, typed-answer evaluation, and policy-constrained local actions. Fresh local verification exercised all four, retained adverse outcomes, and identified the tested source files and artifacts by SHA-256.

The principal improvements are:

- **Honest evaluation status:** Jev's evaluator no longer labels a run PASS merely because requests succeeded without question-level thresholds. JSON, Markdown and CLI output distinguish PASS, FAIL and UNGATED; ungated runs exit 3. Explicit threshold failures still exit 1, and invalid inputs exit 2.
- **Replay provenance:** Jev CLI runs retain exact input/output hashes in a separate deterministic manifest. Replayed response origin is explicitly unverified; a supplied `model` field is not provider authentication.
- **Portfolio reproduction:** a single repository command invokes the existing project workflows, retains commands/logs/timings, checks expected outcomes and actual serialized ticket states, detects source changes during execution, and preserves unsuccessful attempts. It does not replace the projects' evaluation logic or merge their environments.
- **Publication package:** this report, a [news/reviewer briefing](NEWS_READY.md), [reproduction and publication instructions](PUBLICATION_GUIDE.md), [official-source notes](NIW_SOURCE_NOTES.md), and a [compact evidence summary](publication/evidence-2026-10-11.json).

These controls may be useful for making model-related decisions inspectable. **Their usefulness to outside organizations, live-model efficacy, adoption and broader U.S. impact have not been established by this verification.** Shared subject matter is not an implemented integration: the projects were executed separately.

## 2. Project portfolio

| Project and technical documentation | Implemented boundary | Evidence category | What is not demonstrated |
| --- | --- | --- | --- |
| [RELIA](../../ai-workflows/ai-decision-reliability/README.md) | Frozen synthetic commerce evaluation, calibration, input/policy guards, review fixtures, ranking metrics, drift and release/update gates | Five-seed synthetic benchmark and same-environment repeatability | Real-commerce results, fairness across real populations, deployment, independent reproduction, accepted release or reuse rights |
| [experiment-gate](../../ai-workflows/experiment-gate/README.md) | SHIP/HOLD/ROLLBACK/INVALID from aggregate A/B summaries; guardrails, sample-ratio checks and optional variance/sequential methods | Synthetic scenario outcomes and software checks | Effects on a live product; exact guarantees outside the stated statistical assumptions |
| [Jev decision](../../ai-workflows/jev-decision/README.md) | Typed decisions and offline labeled-case evaluation; explicit gating and provenance | Hand-authored response replay, parser/evaluator behavior and reporting correction | Live Jev/OpenAI performance, calibrated provider probabilities or an authenticated provider response |
| [decision-control](../../ai-workflows/decision-control/README.md) | Frozen local policy evidence, durable review and atomic SQLite ticket reassignment | Real local database changes driven by illustrative recommendations; adverse policy evaluation and replay | Reviewer authentication, external-service execution, distributed exactly-once behavior or deployed safety |

The root `src/` material remains a legacy research workbench. It is not presented as a validated product or included in this four-project verification; its separate [bounded baseline](../../src/README.md#baseline-check) remains available. Project boundaries and CI routing are defined in [workspace.json](../../workspace.json).

RELIA is candidate **0.1.5**, specification **0.1.3**, still **unreleased**. Its [license status](../../ai-workflows/ai-decision-reliability/LICENSE) grants no license pending clearance; the root MIT license does not override it. This report does not publish or accept a standalone RELIA distribution. All other permissions remain governed by the relevant project files and upstream rights.

## 3. Verification method and identity

The complete local run was recorded at **2026-10-12T03:37:53.623240+00:00 (UTC)**; the report's preparation date is the local calendar date. The source HEAD at start was `18e4f6aaf89662663d828176a2757329e4a89af2`, but the verified worktree included the new changes. **That HEAD alone does not identify the tested code.** The public evidence summary lists SHA-256 for all **117** project/tooling/workflow source files checked by the collector and the full retained record's hash.

```bash
uv run --no-project --python 3.11 python scripts/publication_evidence.py \
  --out /tmp/ai-decision-evidence-new
uv run --no-project --python 3.11 python scripts/publication_evidence.py \
  --verify /tmp/ai-decision-evidence-new
```

Use a new external output directory, with an existing parent. The actual local run was retained as `ai-decision-evidence-20261011-a`. Its full `EVIDENCE.json` SHA-256 is `ab4d344bcfc47ee96e0237747ba8a8b21cc2e2923901711c765afc89fd736cfc`.

The driver used CPython **3.11.17** on **macOS 27.0.1 arm64**. RELIA's frozen environment used CPython **3.13.7**, NumPy **2.5.3**, SciPy **1.18.1**, scikit-learn **1.9.1**, and four numerical-library thread limits set to 1. Its lockfile hash was `8214e40c49f0f8e955055096a1eb773892c2367955f16691f802f1d9e91222cf`. Dependencies/caches were available on the existing development machine; this was not a clean-machine or unaffiliated reproduction.

| Exercised suite | Observed result | Runtime scope |
| --- | --- | --- |
| RELIA | 38 passed | Frozen project environment, Python 3.13.7 |
| experiment-gate | 62 passed | Python 3.11.17 |
| Jev decision | 82 passed | Python 3.11.17; additional full suite also passed under Python 3.13.16 |
| decision-control | 79 passed | Python 3.11.17 |
| Delivery controller / workspace / evidence integrity | 26 / 47 / 6 passed | Python 3.11.17; workspace consistency command also passed |
| RELIA export fixtures | 10 passed | Disposable fixture exports only, not an accepted release export |

The actual CLI workflows—not only tests—were then executed. The evidence directory retained 86 hashed files; its integrity-verification command succeeded. Raw logs and full artifacts are retained locally and are **not included** in the compact public summary. An investigator can reproduce the workflow; this report does not claim an external reviewer has done so. Hashes detect changes against a retained record, not forgery, authorship, rights or reviewer identity.

The evaluation-status defect was also reproduced against the original HEAD implementation: 12 replayed cases without thresholds returned `pass: true`. The changed evaluator on those same inputs returned `status: UNGATED`. The fresh command-line run without thresholds returned exit 3, while the explicitly gated bundled fixture returned PASS/0.

## 4. Observed results, including adverse outcomes

### RELIA: synthetic benchmark, not commercial performance

The generated partitions contained 108,228 training, 12,005 calibration and 11,927 held-out test rows, with time boundaries at days 72 and 96. Nine primary release gates passed on the worst of five seeds. The boundary review fixture routed 12/12 required cases and 0/4 nonrequired controls.

| Held-out synthetic metric | Logistic baseline, mean | Gradient-boosted candidate, mean |
| --- | ---: | ---: |
| Log loss | 0.568787 | 0.560399 |
| Brier score | 0.190388 | 0.188531 |
| ECE, 15 bins | 0.014760 | 0.015067 |
| Ranking NDCG@10 | 0.910534 | 0.920771 |
| Ranking MRR | 0.925558 | 0.932689 |

Candidate ECE was slightly worse on average than the baseline; passing a ceiling is not evidence of improving every metric. Five seeds are repeated training runs on the defined synthetic dataset, not independent real-world trials or confidence intervals for commercial benefit.

Two fresh runs produced byte-identical `results.json` and `MANIFEST.json`. The results hash was `459b6600c06e15ab92bfd71a9959e624412b9fb19a566f2027f20367b2862a8c`, and the dataset hash was `c49c2a981d6f8e34fe310b185ee28279c5e3b6fc27f0c547ef822e31235d1abe`. Machine-dependent runtime files are excluded from the equality claim. No cross-platform stored-reference comparison was completed in this work.

The guarded later-period update was **REJECT_UPDATE_KEEP_CURRENT_REFERENCE**: worst-seed log-loss delta against current reference was **+0.002229**, violating the nonpositive-delta gate; worst-slice ECE was **0.069241**, exceeding **0.05**. Eight offer-model gates applied; ranking was excluded from that update. The retained primary run also reported drift **WARN** for the seed-11 record. The failed update is evidence of the rejection path, not a defect to conceal or a claim that a deployed system avoided harm.

### experiment-gate: retain all four decision classes

| Synthetic scenario | Observed disposition |
| --- | --- |
| win | SHIP |
| flat | HOLD |
| cuped | HOLD |
| guardrail-breach | ROLLBACK |
| regression | ROLLBACK |
| early-regression | ROLLBACK |
| srm | INVALID |

These show the implemented rules on generated summaries. They do not measure an actual experiment's lift. The project's large-sample, covariate, sequential-monitoring and sample-ratio limitations remain applicable.

### Jev: distinguish demonstration, explicit gate and model evidence

The 12 hand-authored bundled response cases passed their explicit requirements; removing those requirements produced UNGATED. Both runs retained provenance and per-case outputs. Replay can establish parser/evaluator behavior, but neither a good fixture score nor a response's model identifier establishes that Jev or OpenAI produced it. No live provider was called. A PASS can check a sample-count bound alone; it means the specified checks passed, not that the thresholds are scientifically adequate.

### decision-control: actual local effects, constrained trust boundary

ALLOW moved a ticket to support and incremented its revision to 1. REVIEW persisted across database reopen, was approved by the local operator label, moved the ticket to engineering at revision 1, and returned the same recorded result on repeated execution. DENY and ABSTAIN left their tickets in intake at revision 0. Serialized records were replayed.

The adverse labeled-policy fixture intentionally returned **FAIL/1**. Replaying its evidence returned valid evidence while retaining FAIL; replay validity is not policy acceptance. Recommendations and labels were illustrative. Local SQLite atomicity and caller-supplied reviewer labels are not external action guarantees or authenticated identity.

## 5. Relevance to a specific proposed U.S. endeavor

**Drafting hypothesis, not a confirmed personal commitment:** develop and evaluate reproducible controls for bounded AI-assisted commerce decisions, disseminating inspectable methods and rights-cleared tools for offer/ranking evaluation, experiment promotion decisions and approval-constrained actions.

The technical motivation is to distinguish model output from authority, retain the basis for go/no-go decisions, expose missing uncertainty, and preserve unfavorable evaluations. [NIST AI RMF 1.0](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf) provides a relevant voluntary risk-management vocabulary. It does not certify this work or establish its national importance. NIST's [current framework page](https://www.nist.gov/itl/ai-risk-management-framework) says the 1.0 framework is being revised; this report does not treat an in-progress revision as a completed standard.

| Selected NIST outcomes | Portfolio evidence | Unresolved work |
| --- | --- | --- |
| MAP: intended context and limits | Bounded workflows, input assumptions, explicit excluded claims | Confirm real user workflows and representative target populations |
| MEASURE: documented evaluation | Held-out synthetic metrics, baselines, thresholds, adverse results, repeatable artifacts | Authorized representative application evaluation; independent labels and assessment |
| GOVERN: responsibility and third-party risks | Frozen local policies, project boundaries, rights/status disclosure | Operational roles, authenticated oversight, upstream permissions and governance assessment |
| MANAGE: decisions and residual risks | Rejected update, rollback/hold outcomes, review/replay records | Real operational monitoring, incident evidence and measurable outcomes |

This is an author mapping to selected outcomes, not full AI RMF implementation or regulatory compliance. Exact subcategory citations and qualifications are in the [source notes](NIW_SOURCE_NOTES.md#4-technical-evidence-useful-nist-crosswalk-not-certification).

## 6. EB-2 NIW evidence mapping and limits

The [USCIS Policy Manual, Volume 6, Part F, Chapter 5](https://www.uscis.gov/policy-manual/volume-6-part-f-chapter-5), §§D.1–D.3, first requires qualification for the underlying EB-2 classification, then evaluates the three NIW prongs. It distinguishes a specific endeavor from an occupation and its broader prospective implications from benefits confined to one employer or its clients. An AI label, public repository, test result or self-published article is not an eligibility determination.

| Issue | What this report can document | Facts not established here |
| --- | --- | --- |
| Underlying EB-2 classification | Technical subject matter only | Qualifying degree/equivalency and specialty experience, or applicable exceptional-ability evidence and final merits |
| Substantial merit and national importance | Specific technical problems, scoped capabilities and a proposed dissemination mechanism | Supported broader U.S. implications of this individual's endeavor, credible external interest and transferability |
| Well positioned to advance the endeavor | Inspectable progress, software behavior and an evidence-preservation method | Individually corroborated contribution/role, relevant achievements, feasible resources and confirmed U.S. work plan |
| Balance favors waiving job offer/labor certification | An organized technical record for individualized assessment | Person-specific waiver-balance facts, labor-certification practicality, any evidenced urgency and implications for U.S. workers |

This report may help explain technical progress; it is **author-produced evidence**. Genuine external assessment, use, interest or recognition must be documented separately. An AI-agent review is not a human expert endorsement. Authorship should be corroborated through actual contribution records and authorized supporting evidence rather than inferred from repository ownership. No independent reviewer, customer, citation, economic benefit, press coverage or legal finding is claimed.

## 7. Next evidence priorities and release boundaries

These are recommended acceptance milestones, not promised results or already funded activities:

1. **Confirm the personal endeavor and eligibility record:** identify intended U.S. activities, role, users, resources and implementation route; collect authenticated degree/experience or exceptional-ability evidence privately with appropriate counsel.
2. **Resolve rights and artifact acceptance:** obtain RELIA's required clearance, freeze an exact candidate, complete its separate reproduction and acceptance procedure, and only then publish the accepted standalone identity/license/tag. This report does not bypass that process.
3. **Obtain genuine outside assessment:** a qualified person actually executes or reviews identified artifacts, discloses relationships/interests and methods, records defects and unfavorable outcomes, and consents to publication. No prewritten favorable endorsement.
4. **Demonstrate authorized application usefulness:** use representative held-out data and independent labels; freeze policies and thresholds before examining results; evaluate errors, uncertainty and residual security/privacy/bias risks. Keep synthetic results separate from these future outcomes.
5. **Corroborate broader implications and dissemination:** retain actual user interest/use, attributable outcomes, transferable methods and any independent editorial coverage. Document publication URLs/dates/disclosures; paid or syndicated placement must not be relabeled independent recognition.

The [news briefing](NEWS_READY.md) is ready for attributed first-party outreach. The report has been published on the repository's development branch with a review PR; exact public locations and content-identity checks are in the [publication record](PUBLICATION_RECORD.md). This is not a merged release, package acceptance or proof of independent news coverage. Repository-wide dependency security has not been cleared and must be triaged before production-readiness claims.

## Sources and disclosure

Primary legal and standards sources were accessed on 2026-10-11: [USCIS policy manual](https://www.uscis.gov/policy-manual/volume-6-part-f-chapter-5), [USCIS January 15, 2025 guidance update](https://www.uscis.gov/newsroom/alerts/uscis-updates-guidance-on-eb-2-national-interest-waiver-petitions), [NIST AI RMF 1.0](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf), [NIST Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) and [current NIST framework status](https://www.nist.gov/itl/ai-risk-management-framework). The [source notes](NIW_SOURCE_NOTES.md) provide section-level legal/standards citations, currency and access limitations. Local implementation claims derive from the linked project documentation and the identified fresh run, not these agencies' endorsement.
