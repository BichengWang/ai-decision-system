# Medium story: calibration milestone

Published on 2026-11-01 (U.S. Pacific; `article:published_time` 2026-11-02T06:42:31Z) at
[medium.com/@bichengwang17/…-27eee2999a26](https://medium.com/@bichengwang17/two-calibrators-six-cases-opposite-verdicts-27eee2999a26),
first as "Two Calibrators, Six Cases, Opposite Verdicts". On 2026-11-02 the story, title,
subtitle and cover were replaced by the ones below, without the kicker, so it announces
the milestone; the run's analysis moved to [Run notes](#run-notes-repo-only). The URL
slug keeps the first title. It is a follow-up to the 2026-10-22 "Decisions you can
replay" series, not the 0.2.0 launch post in [`medium.md`](medium.md), and covers
probability calibration in `jev-decision-eval`
([#293](https://github.com/BichengWang/ai-decision-system/pull/293)). Every output in the
story comes from the [run below](#the-run-as-made).

## Headline

```text
KICKER:   Decisions you can replay
TITLE:    My AI Decision Records Now Calibrate Model Confidence
SUBTITLE: jev-decision-eval fits a calibration on one labeled set, gates on held-out cases, and keeps both runs as records anyone can verify.
```

Cover: [`calibration-cover.png`](calibration-cover.png), lines copied from the run below.
Alt text: "Terminal output: jev-decision-eval fits an isotonic calibration on six support
tickets, applies it to six held-out tickets and passes a refund calibrated ECE gate of
0.15 at 0.1139; jev-decision-verify then prints verified for both runs."

Tags: Machine Learning, MLOps, AI Governance, Python, Open Source.

## Story

A model answers "yes, refund this customer" with probability 0.95, and a policy acts on
anything above 0.9. That threshold works when answers at 0.95 are right about 95% of the
time. As of this week, `jev-decision-eval` can calibrate those probabilities and keep
the proof: probability calibration has landed in ai-decision-system.

This article was drafted with the help of an AI writing assistant. The commands and
outputs come from a run on 2026-11-01 at commit `682f382`, on the repository's bundled
support-ticket example.

A follow-up to *Decisions you can replay*, a five-part series on records for
AI-assisted go/no-go decisions.

### What shipped

- **Two standard methods.** Isotonic regression and Platt scaling, picked with one flag:
  `--fit-calibration isotonic` or `--fit-calibration platt`.
- **Fit on one set, measure on another.** Calibrated ECE, Brier score and log loss are
  reported on held-out cases, where they mean something.
- **Gates on calibrated scores.** One line of JSON sets the bar, for example a refund
  calibrated ECE of at most 0.15.
- **Leak protection built in.** A calibration applied to any case it was fitted on is
  refused.
- **Records anyone can recompute.** `calibration.json` keeps the method, each map and the
  SHA-256 of the data it was fitted on. `jev-decision-verify` refits it, re-applies it and
  catches a hand-edited score.

### Two commands

[jev-decision](https://github.com/BichengWang/ai-decision-system/tree/682f382/ai-workflows/jev-decision)
asks a model typed questions and records the answers. Its bundled example has 12 labeled
support tickets. Fit on the first six, then gate on the other six:

```text
jev-decision-eval --questions $E/support-ticket.json \
  --cases fit-cases.jsonl --responses fit-responses.jsonl \
  --fit-calibration isotonic --out fit-isotonic

jev-decision-eval --questions $E/support-ticket.json \
  --cases held-cases.jsonl --responses held-responses.jsonl \
  --calibration fit-isotonic/calibration.json --require gate.json --out held-isotonic
```

```text
PASS 9562afb6a4868ff9bf0ade8ce212523217d41e89af444e3cc3bc5f572a9e283b
| refund.calibrated_ece | max 0.15 | 0.1139 | pass |
```

Anyone holding the two directories can check them:

```text
fit-isotonic: verified
held-isotonic: verified
```

The held-out run records the hash of the calibration it applied, so the two runs stay
linked.

### Use it where the decision is made

Load the calibration and compare the calibrated probability with your threshold:

```python
from pathlib import Path
from jevdecision.calibration import load

calibration = load(Path("fit-isotonic/calibration.json").read_bytes())
p = calibration.calibrate("refund", decision["refund"].probability)
```

### Try it

```text
git clone https://github.com/BichengWang/ai-decision-system.git
pip install ./ai-decision-system/ai-workflows/jev-decision
```

The [calibration section](https://github.com/BichengWang/ai-decision-system/blob/682f382/ai-workflows/jev-decision/README.md#calibrating-the-probabilities)
of the README covers both methods and the record format.

If you put a threshold on model confidence, I would like to hear how you measure it.

### The series

Decisions you can replay, in five parts:

1. [Your AI Shipped a Model. Can You Prove Why Six Months Later?](https://medium.com/@bichengwang17/your-ai-shipped-a-model-can-you-prove-why-six-months-later-da0ca762c808)
2. [A Hash Won't Stop the Forger Who Uses Your Own Tool](https://medium.com/@bichengwang17/a-hash-wont-stop-the-forger-who-uses-your-own-tool-3672ce42f390)
3. [One 2.0 Broke My JSON Hash in Node.js](https://medium.com/@bichengwang17/one-2-0-broke-my-json-hash-in-node-js-571078ea7f58)
4. [5 of 7 Decisions Made on a Mac Failed to Replay on Linux](https://medium.com/@bichengwang17/5-of-7-decisions-made-on-a-mac-failed-to-replay-on-linux-a9f5e5d192a8)
5. [Your LangGraph Approval Is Not Evidence](https://medium.com/@bichengwang17/your-langgraph-approval-is-not-evidence-3bb623a387f3)

## Run notes (repo only)

Analysis from the same run, kept here rather than in the public story. The model answers
are hand-written fixtures in Jev's format, not output from any model, so no model's
calibration was measured. Held-out metrics, lower is better:

```text
Held-out metric              Raw      Isotonic   Platt
refund ECE                   0.145    0.1139     0.2544
refund Brier                 0.06348  0.0697     0.095
refund log loss              0.1996   0.1793     0.3298
department ECE               0.105    0.1667     0.04167
frustration ECE              0.2917   0          0.125
Gate: refund ECE <= 0.15              PASS       FAIL
```

- Platt's smoothed targets with 2 positives and 4 negatives are 3/4 and 1/6; its refund
  slope came out near 0.5 and pulled 0.97 to 0.814.
- Isotonic's frustration ECE of 0 comes from a flat "always 1.0" map meeting six
  all-correct held-out answers; a gate needs a bound on `n` as well as the score.
- Six held-out cases cannot rank the methods; Niculescu-Mizil and Caruana
  ([ICML 2005](https://icml.cc/Conferences/2005/proceedings/papers/079_GoodProbabilities_NiculescuMizilCaruana.pdf))
  found Platt ahead below roughly 200 to 1,000 calibration cases.
- A hand-edited held-out `calibrated_ece` with a recomputed provenance hash fails
  `jev-decision-verify` with `mismatch: evaluation.json:questions`.
- The feature is on `main` and unreleased until 0.2.0; no outside user has run it.

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
