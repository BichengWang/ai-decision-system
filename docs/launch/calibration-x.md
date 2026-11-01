# X draft: calibration follow-up

Draft for the owner to rewrite in their own words and post from
[@BichengW81192](https://x.com/BichengW81192). Nothing here has been posted. It links the
Medium follow-up in [`calibration-medium.md`](calibration-medium.md), so publish that
first and replace `[Medium link]` with its URL. Every number comes from
[the run in that file](calibration-medium.md#the-run-as-made).

Each post fits the 280-character limit of an account without X Premium (X counts every
link as 23 characters). Post them as one thread, replying to the previous post each time.
Before posting, check the current [X Rules](https://help.x.com/en/rules-and-policies/x-rules).

## Thread

```text
1/ Same six labeled cases, two standard calibration methods. On held-out data, isotonic passed my gate (refund ECE 0.114, bound 0.15) and Platt failed it (0.254).

The result I trust least from that run is a perfect 0.
```

```text
2/ A threshold like "act if confidence > 0.9" means something only if answers at 0.9 are right about 90% of the time. So jev-decision-eval now fits a calibration map on one labeled set and measures it on another, and keeps both runs as records.
```

```text
3/ Setup: 12 support tickets with hand-written answers, not a real model. Fit on t01 to t06, hold out t07 to t12.

Refund ECE: raw 0.145, isotonic 0.114, Platt 0.254
Department ECE: raw 0.105, isotonic 0.167, Platt 0.042

No method won every row.
```

```text
4/ Why Platt lost on refund: with 2 refunds and 4 non-refunds, its smoothed targets are 3/4 and 1/6, so the slope came out near 0.5 and 0.97 became 0.81. These held-out answers were confident and mostly right, so squeezing them cost more than it fixed.
```

```text
5/ The perfect 0: all six fitting answers for frustration were right, so isotonic learned "always 1.0". The six held-out answers were right too, so its ECE was 0.

A threshold on that probability would pass anything. Gate on n as well as on the score.
```

```text
6/ Six cases can't rank the methods. Niculescu-Mizil and Caruana (ICML 2005) found Platt ahead below roughly 200 to 1,000 calibration cases.

What the run does show: you only learn which method your gate accepts on cases the fit never saw.
```

```text
7/ What the tool enforces:
• The fitting run reports no calibrated metrics
• Applying a calibration to a case it was fitted on exits 2
• jev-decision-verify refits it; a hand-edited score with a recomputed hash fails

On main, unreleased until 0.2.0. No outside users yet.
```

```text
8/ Write-up with every command and number: [Medium link]

Code: https://github.com/BichengWang/ai-decision-system

If you put a threshold on model confidence, how many labeled cases was it measured on?
```

## Single post

For a quote-post or a reply where a thread does not fit:

```text
Same six labeled cases, two calibration methods: on held-out data isotonic passed my gate and Platt failed it. The number I trust least is isotonic's perfect 0 on a question where every answer happened to be right.

Write-up: [Medium link]
```

## Notes for the owner

- Recount after rewriting. Replacing `[Medium link]` with a URL counts as 23 characters.
- Do not add counts of stars, downloads or views, or claims about users.
