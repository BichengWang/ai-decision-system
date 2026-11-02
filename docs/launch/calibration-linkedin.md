# LinkedIn post: calibration follow-up

[Posted](https://www.linkedin.com/feed/update/urn:li:activity:7522911383903207424/) on
2026-11-01 from the owner's profile, as written below with `[Medium link]` replaced by
the [Medium story](https://medium.com/@bichengwang17/two-calibrators-six-cases-opposite-verdicts-27eee2999a26).
Every number comes from [the run in the Medium file](calibration-medium.md#the-run-as-made).

## Post

````text
Same six labeled cases. Two standard calibration methods. On held-out data, one passed my gate and the other failed it.

I added probability calibration to jev-decision, the part of ai-decision-system that records typed model answers. You fit a map on one labeled set, measure it on another, and both runs become records someone else can recompute.

On the bundled 12-ticket example (hand-written answers, not a real model), split 6 and 6:
• Refund ECE: raw 0.145, isotonic 0.114, Platt 0.254
• Gate of ECE ≤ 0.15: isotonic PASS, Platt FAIL
• No method won every metric. Isotonic made refund Brier and department ECE worse; Platt helped the other two questions.

The number I trust least is a perfect 0. Every fitting answer for one question was right, so isotonic learned "always 1.0", and the six held-out answers happened to be right too. A threshold on that probability would pass anything.

What the tool enforces:
• The fitting run reports no calibrated metrics.
• Applying a calibration to a case it was fitted on exits 2.
• jev-decision-verify refits or re-applies it. A hand-edited score with a recomputed hash fails.

Six cases can't rank the methods; Niculescu-Mizil and Caruana found Platt ahead below roughly 200 to 1,000 calibration cases. What the run does show is that you only learn which one your gate accepts by measuring on cases the fit never saw.

It's on main and unreleased until 0.2.0. No outside user has run it yet.

The write-up, with every command and number:
[Medium link]

Code: https://github.com/BichengWang/ai-decision-system

If you put a threshold on model confidence, how many labeled cases was it measured on?

#MachineLearning #MLOps #AIGovernance #OpenSource
````

## Notes for the owner

- The post stays under LinkedIn's 3,000-character limit; check again after rewriting.
- LinkedIn shows bullets as typed; keep the `•` characters or switch to plain lines.
- Do not add counts of stars, downloads or views, or claims about users.
