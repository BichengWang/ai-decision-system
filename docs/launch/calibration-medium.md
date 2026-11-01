# Medium draft: calibration follow-up

Draft for the owner to rewrite in their own words and publish from their own Medium
account. Nothing here has been published. It is a follow-up to the 2026-10-22
"Decisions you can replay" series, not the 0.2.0 launch post in [`medium.md`](medium.md),
and it covers one feature: probability calibration in `jev-decision-eval`
([#293](https://github.com/BichengWang/ai-decision-system/pull/293)). Every number in
the story comes from the [run below](#the-run-as-made).

Before publishing:

- Medium's [AI content policy](https://help.medium.com/hc/en-us/articles/22576852947223-Artificial-Intelligence-AI-content-policy)
  asks a story with AI assistance to say so within its first two paragraphs. The story
  keeps the disclosure line the series used; drop it only if no AI-written text remains.
- Medium's editor does not render Markdown tables. The two tables are code blocks so
  they paste as monospaced text; check them after pasting.
- In the editor, type the kicker first and format it small "t", then the title as the
  large "T" line, then the subtitle small "t" directly under it.
- Re-run the [commands below](#the-run-as-made) if `main` has moved past `682f382`, and
  update the commit in the story's links and closing line.
- Do not add counts of stars, downloads or views, or claims about users.

## Headline

```text
KICKER:   Decisions you can replay
TITLE:    Two Calibrators, Six Cases, Opposite Verdicts
SUBTITLE: I added confidence calibration to my AI decision records. The held-out run, not the fit, decided whether a threshold could trust it.
```

Alternative titles, same story: "A Perfect Calibration Score From Six Cases Is a
Warning"; "Your Model Says 0.95. Who Measured That?"

Cover: a screenshot of the first table below (held-out metrics). Alt text: "Table of
held-out calibration metrics on six support tickets: raw, isotonic and Platt. Isotonic
passes a refund ECE gate of 0.15 at 0.1139; Platt fails it at 0.2544."

Tags: Machine Learning, MLOps, AI Governance, Python, Open Source.

## Story

A model answers "yes, refund this customer" with probability 0.95, and a policy acts on
anything above 0.9. That threshold means something only if answers at 0.95 are right
about 95% of the time. No provider promises that, and my own tools had been passing
those numbers straight into thresholds.

So I added calibration to `jev-decision-eval`: fit a monotone map on one labeled set,
measure it on another, and keep both runs as records someone else can recompute. The
first run surprised me. Fitted on the same six cases, isotonic regression passed my gate
on held-out data and Platt scaling failed it.

This article was drafted with the help of an AI writing assistant. The commands and
numbers come from a run on 2026-11-01 at commit `682f382`, recorded in full in the
repository. The model answers in it are hand-written fixtures, not output from any model.

A follow-up to *Decisions you can replay*, a five-part series on records for
AI-assisted go/no-go decisions.

### The setup

[jev-decision](https://github.com/BichengWang/ai-decision-system/tree/682f382/ai-workflows/jev-decision)
asks a model typed questions and records the answer. Its bundled example has 12 support
tickets and three questions: should we refund (yes or no, with a probability), which
department (a choice, with a probability per option) and how frustrated the customer is
(a level on a scale). Every ticket is labeled for all three.

I split the example in half. Tickets t01 to t06 fit the calibration; t07 to t12 are held
out. The gate is one line of JSON: at least six refund cases, and a calibrated expected
calibration error (ECE) of at most 0.15.

```text
jev-decision-eval --questions $E/support-ticket.json \
  --cases fit-cases.jsonl --responses fit-responses.jsonl \
  --fit-calibration isotonic --out fit-isotonic

jev-decision-eval --questions $E/support-ticket.json \
  --cases held-cases.jsonl --responses held-responses.jsonl \
  --calibration fit-isotonic/calibration.json --require gate.json --out held-isotonic
```

The fitting run reports no calibrated metrics at all. Scored on the cases it was fitted
on, a calibrator looks better than it is, so the tool measures it only on cases it has
not seen.

### What the held-out run said

Same six fitting cases, same six held-out cases, two methods. Lower is better in every
row.

```text
Held-out metric              Raw      Isotonic   Platt
refund ECE                   0.145    0.1139     0.2544
refund Brier                 0.06348  0.0697     0.095
refund log loss              0.1996   0.1793     0.3298
department ECE               0.105    0.1667     0.04167
frustration ECE              0.2917   0          0.125
Gate: refund ECE <= 0.15              PASS       FAIL
```

No method won every row. Isotonic improved refund ECE and log loss but made refund Brier
and department ECE worse. Platt made all three refund metrics worse and improved the other
two questions.

The refund probabilities, ticket by ticket, show why:

```text
Ticket  Label  Raw    Isotonic  Platt
t07     no     0.06   0.0       0.165
t08     yes    0.97   1.0       0.814
t09     no     0.02   0.0       0.101
t10     yes    0.40   0.354     0.389
t11     no     0.04   0.0       0.138
t12     yes    0.88   0.962     0.676
```

Platt fits `sigmoid(a * logit(p) + b)` to smoothed targets. With two refunds and four
non-refunds in the fitting set, those targets are 3/4 and 1/6 instead of 1 and 0, so the
fitted slope came out at about 0.5 and pulled every confident answer toward the middle:
0.97 became 0.814. The raw answers on these six tickets were mostly right and confident,
so squeezing them cost more than it fixed.

Isotonic went the other way. Its step map sends anything at or below 0.12 to 0 and
anything at or above 0.91 to 1, which happened to suit these six tickets.

### Six cases cannot pick a method

Niculescu-Mizil and Caruana compared the two methods on eight problems and found that
"when the calibration set is small (less than about 200-1000 cases), Platt Scaling
outperforms Isotonic Regression"
([ICML 2005](https://icml.cc/Conferences/2005/proceedings/papers/079_GoodProbabilities_NiculescuMizilCaruana.pdf)).
Six held-out tickets do not overturn that. Five of six refund answers were right, and the
95% Wilson interval on that accuracy runs from 0.44 to 0.97. One ticket, t10 (a nonprofit
asking for a discount, and for a refund if there is none), carries much of every metric
in the table.

The run supports a narrower claim: which method passes my gate is a fact about these
cases, and I learn it only by measuring on cases the fit never saw.

### The perfect zero

Isotonic scored a calibrated ECE of exactly 0 on frustration. I trust that number least.

All six fitting answers for frustration were correct, so isotonic learned a flat map:
every answer gets probability 1.0. The six held-out answers were also all correct, so a
calibrator that says "always right" was perfectly calibrated on them. On department the
same flat map met one wrong held-out answer (t10 again), and ECE rose from 0.105 to
0.1667. Platt, given the same all-correct fitting set, returned a constant 0.875, its
smoothed hit rate of 7/8.

The score was perfect because the held-out set contained nothing that could fail. A
threshold on that frustration probability would pass every answer. A gate needs a bound
on `n` as well as on the score, and six cases are not enough for a real decision.

### What the record keeps

`calibration.json` holds the method, one map per question with its `n` and positive
count, and the SHA-256 of the fitting run's `cases.jsonl` and `responses.jsonl` with their
case ids. Both runs write `evaluation.json` and `provenance.json`. The held-out run's
input hash for the calibration equals the fitting run's output hash, which links the two
directories.

Three checks come with it:

- A calibration applied to any case it was fitted on is refused. Running it over all 12
  tickets exits 2 with `calibration was fitted on cases of this evaluation (t01, t02, t03,
  t04, t05 and 1 more); evaluate it on held-out cases`.
- `jev-decision-verify --evaluation` refits a fitted calibration from its directory and
  re-applies an applied one. Both directories print `verified`.
- I edited the held-out refund `calibrated_ece` to 0.01 and recomputed its hash in
  `provenance.json`. The verifier re-scored the run and printed
  `mismatch: evaluation.json:questions`, exit 1. A hash shows that bytes changed, not
  who changed them; signing, covered in part 2 of the series, binds a record to a key.

Where the decision is made, load the calibration and compare the calibrated probability
with your threshold:

```python
from pathlib import Path
from jevdecision.calibration import load

calibration = load(Path("fit-isotonic/calibration.json").read_bytes())
p = calibration.calibrate("refund", decision["refund"].probability)
```

### What this does not show

- No model's calibration was measured. The 12 responses are hand-written in Jev's format
  to exercise the code.
- Six held-out cases cannot rank the two methods.
- A calibration holds for the distribution it was fitted on. When the tickets change,
  refit and measure again.
- The feature is on `main` and unreleased until 0.2.0, which is not on PyPI yet.
- No outside user has run it.

### Try it

```text
git clone https://github.com/BichengWang/ai-decision-system.git
pip install ./ai-decision-system/ai-workflows/jev-decision
```

The [full transcript](https://github.com/BichengWang/ai-decision-system/blob/main/docs/launch/calibration-medium.md#the-run-as-made)
runs from a fresh clone, and the
[calibration section](https://github.com/BichengWang/ai-decision-system/blob/682f382/ai-workflows/jev-decision/README.md#calibrating-the-probabilities)
of the README covers both methods and the record format.

If you put a threshold on a model's confidence, how many labeled cases was it measured
on? I would like to hear what your gate checks.

### The series

Decisions you can replay, in five parts:

1. [Your AI Shipped a Model. Can You Prove Why Six Months Later?](https://medium.com/@bichengwang17/your-ai-shipped-a-model-can-you-prove-why-six-months-later-da0ca762c808)
2. [A Hash Won't Stop the Forger Who Uses Your Own Tool](https://medium.com/@bichengwang17/a-hash-wont-stop-the-forger-who-uses-your-own-tool-3672ce42f390)
3. [One 2.0 Broke My JSON Hash in Node.js](https://medium.com/@bichengwang17/one-2-0-broke-my-json-hash-in-node-js-571078ea7f58)
4. [5 of 7 Decisions Made on a Mac Failed to Replay on Linux](https://medium.com/@bichengwang17/5-of-7-decisions-made-on-a-mac-failed-to-replay-on-linux-a9f5e5d192a8)
5. [Your LangGraph Approval Is Not Evidence](https://medium.com/@bichengwang17/your-langgraph-approval-is-not-evidence-3bb623a387f3)

*This article draws on the public ai-decision-system repository at commit 682f382 and on
a run made on 2026-11-01. It omits adoption claims, private data and any claim about a
real model's calibration.*

## The run, as made

Run on 2026-11-01, macOS arm64, Python 3.15.0, in an empty temporary directory, from a
fresh clone of `main` at `682f382` (`jevdecision` reports 0.2.0; it is unreleased). Output
is pasted unedited; exit codes come from the `echo` on the same line as each command.

```text
$ git clone --quiet https://github.com/BichengWang/ai-decision-system.git && git -C ai-decision-system rev-parse --short HEAD
682f382
$ python3 -m venv .venv && . .venv/bin/activate
$ pip install --quiet ./ai-decision-system/ai-workflows/jev-decision
$ E=ai-decision-system/ai-workflows/jev-decision/examples
$ head -6 $E/support-ticket-cases.jsonl > fit-cases.jsonl; head -6 $E/support-ticket-responses.jsonl > fit-responses.jsonl
$ tail -6 $E/support-ticket-cases.jsonl > held-cases.jsonl; tail -6 $E/support-ticket-responses.jsonl > held-responses.jsonl
$ echo '{"questions": {"refund": {"n": {"min": 6}, "calibrated_ece": {"max": 0.15}}}}' > gate.json
$ jev-decision-eval --questions $E/support-ticket.json --cases fit-cases.jsonl --responses fit-responses.jsonl --fit-calibration isotonic --out fit-isotonic; echo "exit code: $?"
UNGATED 73c44102d3e3fd4cd4b6e3f235457f1d00c9c10682c024bc76686acd039ad1fa
  No explicit question metric bounds; descriptive metrics only.
  Replay origin is unverified; supplied responses are not authenticated provider output.
exit code: 3
$ jev-decision-eval --questions $E/support-ticket.json --cases held-cases.jsonl --responses held-responses.jsonl --calibration fit-isotonic/calibration.json --require gate.json --out held-isotonic; echo "exit code: $?"
PASS 9562afb6a4868ff9bf0ade8ce212523217d41e89af444e3cc3bc5f572a9e283b
  Replay origin is unverified; supplied responses are not authenticated provider output.
exit code: 0
$ jev-decision-eval --questions $E/support-ticket.json --cases fit-cases.jsonl --responses fit-responses.jsonl --fit-calibration platt --out fit-platt; echo "exit code: $?"
UNGATED 9bb0c626fe3ed73c712254f8b8f796b4f7f80b8f7c1aae08af00d843454f9c16
  No explicit question metric bounds; descriptive metrics only.
  Replay origin is unverified; supplied responses are not authenticated provider output.
exit code: 3
$ jev-decision-eval --questions $E/support-ticket.json --cases held-cases.jsonl --responses held-responses.jsonl --calibration fit-platt/calibration.json --require gate.json --out held-platt; echo "exit code: $?"
FAIL 9803ce2d0e5f22dfbf9ae10347cdc3e5ca58cd7a79f13932d3eccb962aaaf9ae
  Replay origin is unverified; supplied responses are not authenticated provider output.
  refund.calibrated_ece: 0.2544 fails max 0.15
exit code: 1
$ grep "^| refund\|^| department\|^| frustration" held-isotonic/EVALUATION.md
| refund | noul | 6 | accuracy 0.8333, accuracy_lower 0.4365, accuracy_upper 0.9699, brier 0.06348, log_loss 0.1996, ece 0.145, base_rate 0.5, mean_probability 0.395, refusals 0, refusal_rate 0, calibrated_brier 0.0697, calibrated_log_loss 0.1793, calibrated_ece 0.1139 |
| department | choice | 6 | accuracy 0.8333, accuracy_lower 0.4365, accuracy_upper 0.9699, brier 0.2113, log_loss 0.3546, ece 0.105, refusals 0, refusal_rate 0, calibrated_ece 0.1667 |
| frustration | score | 6 | accuracy 1, accuracy_lower 0.6097, accuracy_upper 1, within_one 1, mae 0.2867, brier 0.1969, log_loss 0.3645, ece 0.2917, refusals 0, refusal_rate 0, calibrated_ece 0 |
| refund.n | min 6 | 6 | pass |
| refund.calibrated_ece | max 0.15 | 0.1139 | pass |
$ grep "^| refund\|^| department\|^| frustration" held-platt/EVALUATION.md
| refund | noul | 6 | accuracy 0.8333, accuracy_lower 0.4365, accuracy_upper 0.9699, brier 0.06348, log_loss 0.1996, ece 0.145, base_rate 0.5, mean_probability 0.395, refusals 0, refusal_rate 0, calibrated_brier 0.095, calibrated_log_loss 0.3298, calibrated_ece 0.2544 |
| department | choice | 6 | accuracy 0.8333, accuracy_lower 0.4365, accuracy_upper 0.9699, brier 0.2113, log_loss 0.3546, ece 0.105, refusals 0, refusal_rate 0, calibrated_ece 0.04167 |
| frustration | score | 6 | accuracy 1, accuracy_lower 0.6097, accuracy_upper 1, within_one 1, mae 0.2867, brier 0.1969, log_loss 0.3645, ece 0.2917, refusals 0, refusal_rate 0, calibrated_ece 0.125 |
| refund.n | min 6 | 6 | pass |
| refund.calibrated_ece | max 0.15 | 0.2544 | FAIL |
$ jev-decision-verify --evaluation fit-isotonic; jev-decision-verify --evaluation held-isotonic; echo "exit code: $?"
fit-isotonic: verified
held-isotonic: verified
exit code: 0
$ jev-decision-eval --questions $E/support-ticket.json --cases $E/support-ticket-cases.jsonl --responses $E/support-ticket-responses.jsonl --calibration fit-isotonic/calibration.json --out leak; echo "exit code: $?"
error: calibration was fitted on cases of this evaluation (t01, t02, t03, t04, t05 and 1 more); evaluate it on held-out cases
exit code: 2
$ cat forge.py
import hashlib, json, sys
d = sys.argv[1]
ev = open(f"{d}/evaluation.json", "rb").read()
new = ev.replace(b'"calibrated_ece":0.11392405063291139', b'"calibrated_ece":0.01', 1)
assert new != ev
open(f"{d}/evaluation.json", "wb").write(new)
prov = json.load(open(f"{d}/provenance.json"))
prov["outputs"]["evaluation.json"]["sha256"] = hashlib.sha256(new).hexdigest()
open(f"{d}/provenance.json", "w").write(json.dumps(prov, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
$ cp -R held-isotonic forged && python3 forge.py forged && jev-decision-verify --evaluation forged; echo "exit code: $?"
forged: mismatch: evaluation.json:questions
exit code: 1
$ cat per-case.py
import json
from jevdecision.calibration import load
iso = load(open("fit-isotonic/calibration.json", "rb").read())
platt = load(open("fit-platt/calibration.json", "rb").read())
labels = {json.loads(l)["id"]: json.loads(l)["labels"]["refund"] for l in open("held-cases.jsonl")}
for line in open("held-responses.jsonl"):
    r = json.loads(line)
    p = r["response"]["answers"]["refund"]["noul"]
    print(r["id"], labels[r["id"]], p, round(iso.calibrate("refund", p), 3), round(platt.calibrate("refund", p), 3))
$ python3 per-case.py
t07 False 0.06 0.0 0.165
t08 True 0.97 1.0 0.814
t09 False 0.02 0.0 0.101
t10 True 0.4 0.354 0.389
t11 False 0.04 0.0 0.138
t12 True 0.88 0.962 0.676
$ cat fit-isotonic/calibration.json
{"fitted_on":{"case_ids":["t01","t02","t03","t04","t05","t06"],"cases_sha256":"41f9fae86ad75f496568a9208710b38db628e42df65ac0e7163d726769b7da47","responses_sha256":"7d6dfadd66d908ffc1bf1c7af6f7c69eba2e320ea7f69163afaac88407de6f2d"},"method":"isotonic","produced_by":{"name":"jevdecision","version":"0.2.0"},"questions":{"department":{"map":{"x":[0.8,0.93],"y":[1.0,1.0]},"n":6,"positives":6,"target":"chosen","type":"choice"},"frustration":{"map":{"x":[0.7,0.95],"y":[1.0,1.0]},"n":6,"positives":6,"target":"chosen","type":"score"},"refund":{"map":{"x":[0.03,0.12,0.91,0.95],"y":[0.0,0.0,1.0,1.0]},"n":6,"positives":2,"target":"yes","type":"noul"}},"schema_version":1}
$ cat fit-platt/calibration.json
{"fitted_on":{"case_ids":["t01","t02","t03","t04","t05","t06"],"cases_sha256":"41f9fae86ad75f496568a9208710b38db628e42df65ac0e7163d726769b7da47","responses_sha256":"7d6dfadd66d908ffc1bf1c7af6f7c69eba2e320ea7f69163afaac88407de6f2d"},"method":"platt","produced_by":{"name":"jevdecision","version":"0.2.0"},"questions":{"department":{"map":{"a":0.0,"b":1.9459101490553132},"n":6,"positives":6,"target":"chosen","type":"choice"},"frustration":{"map":{"a":0.0,"b":1.9459101490553132},"n":6,"positives":6,"target":"chosen","type":"score"},"refund":{"map":{"a":0.4965371975324734,"b":-0.2520599542234457},"n":6,"positives":2,"target":"yes","type":"noul"}},"schema_version":1}
```

`forge.py` and `per-case.py` were written into the run directory before the commands that
show them. The split matches the repository's own calibration conformance vectors
(`ai-workflows/jev-decision/conformance/valid/evaluation-calibration-fitted` and
`-applied`), whose metrics are the same. The `-applied` vector's `evaluation.json` digest
differs from `held-isotonic`'s because its requirement file lists the same two bounds in
the other order, and the report keeps that order.
