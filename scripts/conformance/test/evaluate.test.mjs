// The evaluator against a stub verifier written in Node, so the test needs no Python. The stub
// checks digests, recomputes one decision from one input field, and ignores a free-text label and
// a note, which gives known stale and resealed outcomes for every leaf of the fixture. Two of its
// digests are embedded (not declared in the manifest), as decision-control's Cedar proposal digest
// and Jev's calibration digest are; resealing must recompute them too. The record schema caps the
// label at one character, which the stub never checks, so the hash + schema baseline rejects a
// resealed label edit that the stub accepts.

import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { callerPathComparison, canonicalForms, evaluate, generalize, loadVectors, mutateValue, problems, renderMarkdown, unaccountedDigests } from "../checks/evaluate.mjs";
import { RawNumber } from "../checks/json.mjs";

const run = promisify(execFile);
const EVALUATE = fileURLToPath(new URL("../evaluate.mjs", import.meta.url));
const REPOSITORY = fileURLToPath(new URL("../../..", import.meta.url));
const CHECKS = (name) => pathToFileURL(fileURLToPath(new URL(`../checks/${name}`, import.meta.url))).href;
const sha = (data) => createHash("sha256").update(data).digest("hex");
const ID = "https://github.com/BichengWang/ai-decision-system/schema/demo";

// The stub: exit 2 on unreadable or unsupported input, 1 when a digest or a recomputation
// disagrees, 0 otherwise. `label`, `input.b`, report items and the source note feed nothing.
const STUB = `#!${process.execPath}
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { parseJson } from "${CHECKS("json.mjs")}";
import { canonicalizeRfc8785 } from "${CHECKS("canonical.mjs")}";
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const read = (file) => parseJson(readFileSync(file, "utf8"));
// The first run dies without an exit code, as a run killed by a timeout does; the evaluator retries it.
const marker = new URL("./killed-once", import.meta.url);
if (!existsSync(marker)) {
  writeFileSync(marker, "");
  process.kill(process.pid, "SIGKILL");
}
const args = process.argv.slice(2);
let code;
try {
  if (args[0] === "--dir") {
    const file = (name) => path.join(args[1], name);
    const provenance = read(file("provenance.json"));
    const intact = Object.entries(provenance.outputs).every(([name, entry]) => sha(readFileSync(file(name))) === entry.sha256);
    const report = read(file("report.json"));
    const source = read(file("source.json"));
    code = intact && report.source_sha256 === sha(readFileSync(file("source.json"))) && report.count === report.items.length && source.n === report.items.length ? 0 : 1;
  } else {
    const record = read(args[0]);
    const known = ["schema_version", "input", "decision", "label", "label_sha256", "input_sha256"];
    if (record.schema_version !== 1 || Object.keys(record).some((key) => !known.includes(key))) code = 2;
    else code = sha(canonicalizeRfc8785(record.input)) === record.input_sha256 && sha(canonicalizeRfc8785(record.label)) === record.label_sha256
      && record.decision === (record.input.a > 0 ? "ship" : "hold") ? 0 : 1;
  }
} catch {
  code = 2;
}
process.exit(code);
`;

const INPUT = '{"a":1,"b":"x"}';
const record = (fields) => JSON.stringify({ schema_version: 1, input: JSON.parse(INPUT), decision: "ship", label: "l", label_sha256: sha('"l"'), input_sha256: sha(INPUT), ...fields });
const SOURCE = '{"n":2,"note":"x"}\n';
const REPORT = `{"count":2,"items":["a","b"],"source_sha256":"${sha(SOURCE)}"}\n`;
// The digests the stub checks that the manifest does not declare.
const DEMO_EMBEDDED = {
  demo: [
    { document: ".", value: "/label_sha256", what: "RFC 8785 SHA-256 of the label", derive: (document) => document.label },
    { document: "report.json", value: "/source_sha256", what: "SHA-256 of source.json", covers_file: "source.json" },
  ],
};

function vector(pathName, expect, extra = {}) {
  const exit = { valid: 0, tampered: 1, invalid: 2 }[expect];
  return { path: pathName, expect, verify: { command: ["demo-verify", "{path}"], exit_code: exit }, note: `fixture ${expect}`, ...extra };
}
const RECORD_DOC = [{ path: ".", schema: "demo/schema/record.v1.json", schema_valid: true }];
const bytesDigest = (name) => ({ document: "provenance.json", value: `/outputs/${name}/sha256`, canonicalization: "bytes", covers_file: name });

const MANIFEST = {
  format: 1,
  package: "demo",
  vectors: [
    vector("valid/record.json", "valid", {
      documents: RECORD_DOC,
      digests: [{ document: ".", value: "/input_sha256", covers: "/input", exclude: [], canonicalization: "rfc8785", canonical_file: "valid/record.input.canonical" }],
    }),
    vector("valid/bundle", "valid", {
      verify: { command: ["demo-verify", "--dir", "{path}"], exit_code: 0 },
      documents: [{ path: "provenance.json", schema: "demo/schema/object.v1.json", schema_valid: true }, { path: "report.json", schema: "demo/schema/object.v1.json", schema_valid: true }],
      digests: [bytesDigest("report.json"), bytesDigest("source.json")],
    }),
    // Decision edited and the digests still match: hash + schema accepts it, replay does not.
    vector("tampered/record-decision-edited.json", "tampered", { documents: RECORD_DOC }),
    vector("tampered/record-input-edited.json", "tampered", { documents: RECORD_DOC }),
    // Only the embedded digest is stale.
    vector("tampered/record-label-edited.json", "tampered", { documents: RECORD_DOC }),
    vector("invalid/record-duplicate-key.json", "invalid", { documents: RECORD_DOC }),
    vector("invalid/record-unknown-member.json", "invalid", { documents: [{ ...RECORD_DOC[0], schema_valid: false }] }),
  ],
};

const FILES = {
  "demo/schema/record.v1.json": JSON.stringify({
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $id: `${ID}/record.v1.json`,
    type: "object",
    additionalProperties: false,
    required: ["schema_version", "input", "decision", "label", "label_sha256", "input_sha256"],
    properties: { schema_version: { type: "integer" }, input: { type: "object" }, decision: { type: "string" }, label: { type: "string", maxLength: 1 }, label_sha256: { type: "string" }, input_sha256: { type: "string" } },
  }),
  "demo/schema/object.v1.json": JSON.stringify({ $schema: "https://json-schema.org/draft/2020-12/schema", $id: `${ID}/object.v1.json`, type: "object" }),
  "conformance/manifest.json": JSON.stringify(MANIFEST, null, 2),
  "conformance/valid/record.json": record({}),
  "conformance/valid/record.input.canonical": INPUT,
  "conformance/valid/bundle/source.json": SOURCE,
  "conformance/valid/bundle/report.json": REPORT,
  "conformance/valid/bundle/provenance.json": `${JSON.stringify({ outputs: { "report.json": { sha256: sha(REPORT) }, "source.json": { sha256: sha(SOURCE) } } })}\n`,
  "conformance/tampered/record-decision-edited.json": record({ decision: "hold" }),
  "conformance/tampered/record-input-edited.json": record({ input: { a: 2, b: "x" } }),
  "conformance/tampered/record-label-edited.json": record({ label: "m" }),
  "conformance/invalid/record-duplicate-key.json": record({}).replace('"label":"l"', '"label":"l","label":"l"'),
  "conformance/invalid/record-unknown-member.json": record({ extra: true }),
};

let root;
let bin;
before(() => {
  root = mkdtempSync(path.join(tmpdir(), "evaluate-"));
  for (const [name, text] of Object.entries(FILES)) {
    const file = path.join(root, "ai-workflows/demo", name);
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, text);
  }
  bin = path.join(root, "bin");
  mkdirSync(bin);
  writeFileSync(path.join(bin, "demo-verify"), STUB);
  chmodSync(path.join(bin, "demo-verify"), 0o755);
});
after(() => rmSync(root, { recursive: true, force: true }));

describe("evaluate with a stub verifier", () => {
  let result;
  before(async () => {
    result = await evaluate({ root, bin, jobs: 3, embedded: DEMO_EMBEDDED });
  });

  test("counts vectors and runs each verifier as its manifest says", () => {
    assert.deepEqual(result.counts.total, { valid: 2, tampered: 3, invalid: 2, total: 7 });
    assert.deepEqual(problems(result), []);
    assert.ok(existsSync(path.join(bin, "killed-once")), "a killed run was retried");
    assert.equal(result.mutations.total.stale.errors + result.mutations.total.resealed.errors, 0);
    assert.equal(result.manifests[0].sha256, sha(FILES["conformance/manifest.json"]));
  });

  test("the baseline checks embedded digests and accepts the edited decision that replay rejects", () => {
    const row = (name) => result.baseline.vectors.find((item) => item.path === name);
    assert.equal(row("tampered/record-decision-edited.json").baseline_strict, "accept");
    assert.equal(row("tampered/record-decision-edited.json").verifier_exit_code, 1);
    assert.match(row("tampered/record-input-edited.json").baseline_strict_reasons.join(), /digest \/input_sha256/);
    assert.match(row("tampered/record-label-edited.json").baseline_strict_reasons.join(), /digest \/label_sha256/);
    assert.equal(row("invalid/record-duplicate-key.json").baseline_strict, "reject");
    assert.equal(row("invalid/record-duplicate-key.json").baseline_json_parse, "accept");
    assert.equal(row("invalid/record-unknown-member.json").baseline_json_parse, "reject");
    assert.deepEqual(result.baseline.total.tampered, { vectors: 3, baseline_strict_accepts: 1, baseline_json_parse_accepts: 1, verifier_rejects: 3, verifier_exit_code_as_manifest: 3 });
    assert.equal(result.baseline.total.valid.baseline_strict_accepts, 2);
  });

  test("resealing recomputes embedded digests, so only replay can catch an edit", () => {
    const [bundle, file] = result.mutations.by_type;
    assert.equal(file.record_type, "record.v1");
    assert.equal(file.embedded_digest_leaves_not_mutated, 1);
    assert.equal(file.stale.mutations, 5); // every leaf but the two digests
    assert.equal(file.stale.detected, 5); // the label is held by its embedded digest
    // A stale label_sha256 would have "detected" the label edit: resealing it leaves it to replay.
    assert.deepEqual(file.resealed.undetected_fields, ["/input/a", "/input/b", "/label"]);
    assert.equal(file.resealed.detected, 2); // schema_version and decision
    assert.equal(bundle.record_type, "provenance-dir");
    assert.equal(bundle.embedded_digest_leaves_not_mutated, 1);
    assert.equal(bundle.stale.detected, 5);
    // The note is held only by report.json's embedded SHA-256 of source.json, which is resealed too.
    assert.deepEqual(bundle.resealed.undetected_fields, ["report.json#/items/[]", "source.json#/note"]);
    assert.deepEqual(result.mutations.controls, { runs: 2, accepted: 2, rejected: [], baseline_accepted: 2, baseline_rejected: [] });
    assert.deepEqual([result.mutations.total.stale.detected, result.mutations.total.resealed.detected, result.mutations.total.resealed.mutations], [10, 4, 10]);
    assert.deepEqual(result.mutations.unaccounted_digest_values, []);
  });

  test("the baseline checks every edited record, and its verdicts are crossed with the verifier's", () => {
    const [bundle, file] = result.mutations.by_type;
    const counters = (cross) => Object.fromEntries(["edits", "baseline_rejects", "verifier_rejects", "only_verifier_rejects", "only_baseline_rejects", "both_reject", "both_accept"].map((key) => [key, cross[key]]));
    // Stale: the stale input and label digests give those three edits away to both; only the stub
    // rejects the decision (exit 1) and the schema version (exit 2).
    assert.deepEqual(counters(file.stale.baseline_strict), { edits: 5, baseline_rejects: 3, verifier_rejects: 5, only_verifier_rejects: 2, only_baseline_rejects: 0, both_reject: 3, both_accept: 0 });
    // Resealed: every digest matches again. The label "lx" breaks the schema's maxLength, which the
    // stub ignores; the decision and the version are still rejected by the stub alone.
    assert.deepEqual(file.resealed.baseline_strict, {
      edits: 5, baseline_rejects: 1, verifier_rejects: 2, only_verifier_rejects: 2, only_baseline_rejects: 1, both_reject: 0, both_accept: 2,
      exit_codes: { 0: { baseline_rejects: 1, baseline_accepts: 2 }, 1: { baseline_rejects: 0, baseline_accepts: 1 }, 2: { baseline_rejects: 0, baseline_accepts: 1 } },
      only_baseline_fields: { "/label": 1 },
      only_baseline_reasons: { schema: 1 },
    });
    assert.deepEqual(file.resealed.undetected_field_counts, { "/input/a": 1, "/input/b": 1, "/label": 1 });
    // A directory vector is checked as a whole: provenance.json's stale SHA-256s give every edit away,
    // and once they are resealed the baseline accepts every edit.
    assert.deepEqual(counters(bundle.stale.baseline_strict), { edits: 5, baseline_rejects: 5, verifier_rejects: 5, only_verifier_rejects: 0, only_baseline_rejects: 0, both_reject: 5, both_accept: 0 });
    assert.deepEqual(counters(bundle.resealed.baseline_strict), { edits: 5, baseline_rejects: 0, verifier_rejects: 2, only_verifier_rejects: 2, only_baseline_rejects: 0, both_reject: 0, both_accept: 3 });
    assert.deepEqual(bundle.resealed.undetected_field_counts, { "report.json#/items/[]": 2, "source.json#/note": 1 });
    assert.deepEqual(counters(bundle.files["source.json"].resealed.baseline_strict), { edits: 2, baseline_rejects: 0, verifier_rejects: 1, only_verifier_rejects: 1, only_baseline_rejects: 0, both_reject: 0, both_accept: 1 });
    const { stale, resealed } = result.mutations.total;
    assert.deepEqual(counters(resealed.baseline_strict), { edits: 10, baseline_rejects: 1, verifier_rejects: 4, only_verifier_rejects: 4, only_baseline_rejects: 1, both_reject: 0, both_accept: 5 });
    assert.deepEqual(resealed.baseline_strict.exit_codes, { 0: { baseline_rejects: 1, baseline_accepts: 5 }, 1: { baseline_rejects: 0, baseline_accepts: 3 }, 2: { baseline_rejects: 0, baseline_accepts: 1 } });
    assert.deepEqual(resealed.baseline_strict.only_baseline_fields, { "demo:record.v1:/label": 1 });
    assert.deepEqual(stale.baseline_strict.exit_codes, { 1: { baseline_rejects: 8, baseline_accepts: 1 }, 2: { baseline_rejects: 0, baseline_accepts: 1 } });
    assert.equal(resealed.undetected_field_counts, undefined);
    // The four cells split the verifier's counts exactly.
    for (const row of [...result.mutations.by_type, result.mutations.total]) {
      for (const mode of ["stale", "resealed"]) {
        const cross = row[mode].baseline_strict;
        assert.equal(cross.both_reject + cross.only_verifier_rejects, row[mode].detected);
        assert.equal(cross.only_baseline_rejects + cross.both_accept, row[mode].undetected);
        assert.equal(cross.both_reject + cross.only_baseline_rejects, cross.baseline_rejects);
      }
    }
    const rejected = structuredClone(result);
    rejected.mutations.controls.baseline_rejected = ["demo/valid/record.json"];
    assert.match(problems(rejected).join("\n"), /demo\/valid\/record\.json: the baseline rejects the re-serialized, unmutated vector/);
  });

  test("is deterministic across worker counts", async () => {
    assert.deepEqual(await evaluate({ root, bin, jobs: 1, embedded: DEMO_EMBEDDED }), result);
  });

  test("renders every section", () => {
    const markdown = renderMarkdown(result);
    for (const heading of ["## (a)", "## (b)", "## (c)", "## Record sizes", "## (d)"]) assert.ok(markdown.includes(heading), heading);
    assert.match(markdown, /\| \*\*All\*\* \| \| 2 \| 10 \| \*\*10\/10 \(100\.0%\)\*\* \| \*\*4\/10 \(40\.0%\)\*\* \|/);
    assert.match(markdown, /Digests detect change, not forgery/);
    assert.match(markdown, /`\/label_sha256` \| RFC 8785 SHA-256 of the label \| yes/);
    assert.match(markdown, /### Hash \+ JSON Schema baseline on the edited records/);
    assert.match(markdown, /Stale:\n\n\| Project \| Record type \| Edits \|[^\n]*\n[^\n]*\n(?:[^\n]*\n)*?\| \*\*All\*\* \| \| 10 \| 8 \| 10 \| 2 \| 0 \| 8 \| 0 \|/);
    assert.match(markdown, /Resealed:\n\n(?:[^\n]*\n)*?\| \*\*All\*\* \| \| 10 \| 1 \| 4 \| 4 \| 1 \| 0 \| 5 \|/);
    assert.match(markdown, /\| \| provenance-dir: source\.json \| 2 \| 0 \| 1 \| 1 \| 0 \| 0 \| 1 \|/);
    assert.match(markdown, /Resealed, the baseline rejects 1 \(10\.0%\) of 10 edits and the verifiers 4 \(40\.0%\); 4 \(40\.0%\) are rejected only by the verifier, and 5 \(50\.0%\) pass both\./);
    assert.match(markdown, /\| 0 \| 6 \| 1 \| 5 \|\n\| 1 \| 3 \| 0 \| 3 \|\n\| 2 \| 1 \| 0 \| 1 \|/);
    assert.match(markdown, /Edits only the baseline rejects: 0 stale, 1 resealed \(resealed: demo record\.v1 `\/label` \(1\); reasons: `schema` \(1\)\)\./);
    assert.doesNotMatch(markdown, /Each of them edits `schema_version`/);
    assert.doesNotMatch(markdown, /With the caller's PATH, resealed/);
    // Only schema_version edits that fail the schema get the explanation.
    const versionEdit = structuredClone(result);
    versionEdit.mutations.by_type[1].resealed.baseline_strict.only_baseline_fields = { "/schema_version": 1 };
    assert.match(renderMarkdown(versionEdit), /Each of them edits `schema_version` and fails the schema step/);
    const withCaller = renderMarkdown({ ...result, caller_path: callerPathComparison(result, result) });
    assert.match(withCaller, /With the caller's PATH, resealed: the baseline rejects 1 of 10, the verifiers 4, only the verifier 4, only the baseline 1, and 5 pass both\./);
  });
});

test("the CLI flags a digest it cannot account for, and writes results with latency when asked", async () => {
  // The CLI uses the repository's table, which knows nothing about the demo's embedded digests.
  const out = path.join(root, "out");
  await assert.rejects(run(process.execPath, [EVALUATE, "--root", root, "--bin", bin, "--out", out, "--latency-runs", "1", "--jobs", "2"]), (error) => {
    assert.equal(error.code, 1);
    assert.match(error.stderr, /label_sha256: a 64-hex value that is neither a manifest digest nor in EMBEDDED_DIGESTS/);
    return true;
  });
  const written = JSON.parse(readFileSync(path.join(out, "results.json"), "utf8"));
  assert.deepEqual(written.mutations.unaccounted_digest_values, ["demo/valid/record.json#/label_sha256", "demo/valid/bundle/report.json#/source_sha256"]);
  assert.equal(written.latency.runs_per_vector, 1);
  assert.match(readFileSync(path.join(out, "RESULTS.md"), "utf8"), /Wall time of one verifier process/);
  await assert.rejects(run(process.execPath, [EVALUATE, "--root", root, "--out", out]), (error) => error.code === 2);
});

test("the repository's vectors: forms follow the schema version, and every 64-hex value is accounted for", async () => {
  const { vectors } = await loadVectors(REPOSITORY);
  const forms = canonicalForms(vectors);
  const record = forms.get("decision-control\0record\0/sha256");
  assert.deepEqual([1, 2, 3, 4, 5].map((version) => record.get(version)), ["python-json-v1", "python-json-v1", "python-json-v1", "rfc8785", "rfc8785"]);
  assert.deepEqual(await unaccountedDigests(vectors.filter((vector) => vector.expect === "valid")), []);
});

test("mutations change exactly one value and keep integers and floats apart", () => {
  assert.equal(mutateValue(new RawNumber("2")).text, "3");
  assert.equal(mutateValue(new RawNumber("9007199254740993")).text, "9007199254740994");
  assert.equal(mutateValue(new RawNumber("2.0")).text, "2.125");
  assert.equal(mutateValue(new RawNumber("1e-07")).text, "0.1250001");
  assert.equal(mutateValue(new RawNumber("4e9")).text, "8000000000.0");
  assert.equal(mutateValue(true), false);
  assert.equal(mutateValue(null), "x");
  assert.equal(mutateValue("é"), "éx");
  assert.equal(generalize("/events/12/note"), "/events/[]/note");
});
