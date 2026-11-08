// The evaluator against a stub verifier written in Node, so the test needs no Python. The stub
// checks a digest, recomputes one decision from one input field, and ignores a free-text label,
// which gives known stale and resealed outcomes for every leaf of the fixture.

import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { evaluate, generalize, mutateValue, problems, renderMarkdown } from "../checks/evaluate.mjs";
import { RawNumber } from "../checks/json.mjs";

const run = promisify(execFile);
const EVALUATE = fileURLToPath(new URL("../evaluate.mjs", import.meta.url));
const CHECKS = (name) => pathToFileURL(fileURLToPath(new URL(`../checks/${name}`, import.meta.url))).href;
const sha = (data) => createHash("sha256").update(data).digest("hex");
const ID = "https://github.com/BichengWang/ai-decision-system/schema/demo";

// The stub: exit 2 on unreadable or unsupported input, 1 when a digest or the recomputed decision
// disagrees, 0 otherwise. `label` and `input.b` feed no recomputation.
const STUB = `#!${process.execPath}
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { parseJson } from "${CHECKS("json.mjs")}";
import { canonicalizeRfc8785 } from "${CHECKS("canonical.mjs")}";
import { existsSync, writeFileSync } from "node:fs";
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
    const provenance = read(path.join(args[1], "provenance.json"));
    const intact = Object.entries(provenance.outputs).every(([name, entry]) => sha(readFileSync(path.join(args[1], name))) === entry.sha256);
    const report = read(path.join(args[1], "report.json"));
    code = intact && report.count === report.items.length ? 0 : 1;
  } else {
    const record = read(args[0]);
    const known = ["schema_version", "input", "decision", "label", "input_sha256"];
    if (record.schema_version !== 1 || Object.keys(record).some((key) => !known.includes(key))) code = 2;
    else code = sha(canonicalizeRfc8785(record.input)) === record.input_sha256 && record.decision === (record.input.a > 0 ? "ship" : "hold") ? 0 : 1;
  }
} catch {
  code = 2;
}
process.exit(code);
`;

const INPUT = '{"a":1,"b":"x"}';
const record = (fields) => JSON.stringify({ schema_version: 1, input: JSON.parse(INPUT), decision: "ship", label: "l", input_sha256: sha(INPUT), ...fields });
const REPORT = '{"count":2,"items":["a","b"]}\n';

function vector(pathName, expect, extra = {}) {
  const exit = { valid: 0, tampered: 1, invalid: 2 }[expect];
  return { path: pathName, expect, verify: { command: ["demo-verify", "{path}"], exit_code: exit }, note: `fixture ${expect}`, ...extra };
}
const RECORD_DOC = [{ path: ".", schema: "demo/schema/record.v1.json", schema_valid: true }];

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
      documents: [{ path: "provenance.json", schema: "demo/schema/provenance.v1.json", schema_valid: true }],
      digests: [{ document: "provenance.json", value: "/outputs/report.json/sha256", canonicalization: "bytes", covers_file: "report.json" }],
    }),
    // Decision edited and the digest still matches: hash + schema accepts it, replay does not.
    vector("tampered/record-decision-edited.json", "tampered", { documents: RECORD_DOC }),
    vector("tampered/record-input-edited.json", "tampered", { documents: RECORD_DOC }),
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
    required: ["schema_version", "input", "decision", "label", "input_sha256"],
    properties: { schema_version: { type: "integer" }, input: { type: "object" }, decision: { type: "string" }, label: { type: "string" }, input_sha256: { type: "string" } },
  }),
  "demo/schema/provenance.v1.json": JSON.stringify({ $schema: "https://json-schema.org/draft/2020-12/schema", $id: `${ID}/provenance.v1.json`, type: "object" }),
  "conformance/manifest.json": JSON.stringify(MANIFEST, null, 2),
  "conformance/valid/record.json": record({}),
  "conformance/valid/record.input.canonical": INPUT,
  "conformance/valid/bundle/report.json": REPORT,
  "conformance/valid/bundle/provenance.json": `${JSON.stringify({ outputs: { "report.json": { sha256: sha(REPORT) } } })}\n`,
  "conformance/tampered/record-decision-edited.json": record({ decision: "hold" }),
  "conformance/tampered/record-input-edited.json": record({ input: { a: 2, b: "x" } }),
  "conformance/invalid/record-duplicate-key.json": record({}).replace('"label":"l"', '"label":"l","label":"m"'),
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
    result = await evaluate({ root, bin, jobs: 3 });
  });

  test("counts vectors and runs each verifier as its manifest says", () => {
    assert.deepEqual(result.counts.total, { valid: 2, tampered: 2, invalid: 2, total: 6 });
    assert.deepEqual(problems(result), []);
    assert.ok(existsSync(path.join(bin, "killed-once")), "a killed run was retried");
    assert.equal(result.mutations.total.stale.errors + result.mutations.total.resealed.errors, 0);
    assert.equal(result.manifests[0].sha256, sha(FILES["conformance/manifest.json"]));
  });

  test("the hash + schema baseline accepts the edited decision that replay rejects", () => {
    const row = (name) => result.baseline.vectors.find((item) => item.path === name);
    assert.equal(row("tampered/record-decision-edited.json").baseline_strict, "accept");
    assert.equal(row("tampered/record-decision-edited.json").verifier_exit_code, 1);
    assert.equal(row("tampered/record-input-edited.json").baseline_strict, "reject");
    assert.match(row("tampered/record-input-edited.json").baseline_strict_reasons.join(), /digest \/input_sha256/);
    assert.equal(row("invalid/record-duplicate-key.json").baseline_strict, "reject");
    assert.equal(row("invalid/record-duplicate-key.json").baseline_json_parse, "accept");
    assert.equal(row("invalid/record-unknown-member.json").baseline_json_parse, "reject");
    assert.deepEqual(result.baseline.total.tampered, { vectors: 2, baseline_strict_accepts: 1, baseline_json_parse_accepts: 1, verifier_rejects: 2, verifier_exit_code_as_manifest: 2 });
  });

  test("stale edits are caught by the digest, resealed edits only where replay depends on the field", () => {
    const [bundle, file] = result.mutations.by_type;
    assert.equal(file.record_type, "record.v1");
    assert.equal(file.stale.mutations, 5); // every leaf but the digest itself
    assert.equal(file.stale.detected, 4);
    assert.deepEqual(file.stale.undetected_fields, ["/label"]);
    assert.equal(file.resealed.detected, 2); // schema_version and decision
    assert.deepEqual(file.resealed.undetected_fields, ["/input/a", "/input/b", "/label"]);
    assert.equal(bundle.record_type, "provenance-dir");
    assert.equal(bundle.stale.detected, 3);
    assert.deepEqual(bundle.resealed.undetected_fields, ["report.json#/items/[]"]);
    assert.deepEqual(result.mutations.controls, { runs: 2, accepted: 2, rejected: [] });
    assert.equal(result.mutations.total.stale.mutations, 8);
    assert.equal(result.mutations.total.stale.detected, 7);
    assert.equal(result.mutations.total.resealed.detected, 3);
  });

  test("renders every section", () => {
    const markdown = renderMarkdown(result);
    for (const heading of ["## (a)", "## (b)", "## (c)", "## Record sizes", "## (d)"]) assert.ok(markdown.includes(heading), heading);
    assert.match(markdown, /\| \*\*All\*\* \| \| 2 \| 8 \| \*\*7\/8 \(87\.5%\)\*\* \| \*\*3\/8 \(37\.5%\)\*\* \|/);
    assert.match(markdown, /Digests detect change, not forgery/);
  });

  test("the CLI writes the same results with another worker count, plus latency when asked", async () => {
    const out = path.join(root, "out");
    const { stdout } = await run(process.execPath, [EVALUATE, "--root", root, "--bin", bin, "--out", out, "--latency-runs", "1", "--jobs", "2"]);
    assert.match(stdout, /mutations: stale 7\/8 detected \(87\.5%\), resealed 3\/8 \(37\.5%\)/);
    const { latency, ...written } = JSON.parse(readFileSync(path.join(out, "results.json"), "utf8"));
    assert.deepEqual(written, JSON.parse(JSON.stringify(result)));
    assert.equal(latency.runs_per_vector, 1);
    assert.equal(latency.by_type.length, 2);
    assert.match(readFileSync(path.join(out, "RESULTS.md"), "utf8"), /Wall time of one verifier process/);
    await assert.rejects(run(process.execPath, [EVALUATE, "--root", root, "--out", out]), (error) => error.code === 2);
  });
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
