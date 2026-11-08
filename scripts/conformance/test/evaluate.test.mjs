// The evaluator against a stub verifier written in Node, so the test needs no Python. The stub
// checks digests, recomputes one decision from one input field, and ignores a free-text label and
// a note, which gives known stale and resealed outcomes for every leaf of the fixture. Two of its
// digests are embedded (not declared in the manifest), as decision-control's Cedar proposal digest
// and Jev's calibration digest are; resealing must recompute them too.

import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { canonicalForms, evaluate, generalize, loadVectors, mutateValue, problems, renderMarkdown, unaccountedDigests } from "../checks/evaluate.mjs";
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
    properties: { schema_version: { type: "integer" }, input: { type: "object" }, decision: { type: "string" }, label: { type: "string" }, label_sha256: { type: "string" }, input_sha256: { type: "string" } },
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
    assert.deepEqual(result.mutations.controls, { runs: 2, accepted: 2, rejected: [] });
    assert.deepEqual([result.mutations.total.stale.detected, result.mutations.total.resealed.detected, result.mutations.total.resealed.mutations], [10, 4, 10]);
    assert.deepEqual(result.mutations.unaccounted_digest_values, []);
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
