// End-to-end tests for the checker: a small valid conformance tree is generated in a temp
// directory (expected digests are computed from literal canonical strings, not by the library
// under test), then broken one way at a time. Each break must be reported.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, beforeEach, describe, test } from "node:test";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { checkRepository } from "../checks/conformance.mjs";

const run = promisify(execFile);
const VERIFY = fileURLToPath(new URL("../verify.mjs", import.meta.url));
const sha = (data) => createHash("sha256").update(data).digest("hex");
const ID = "https://github.com/BichengWang/ai-decision-system/schema/demo";
const WRONG = "0".repeat(64);

// Canonical forms written out by hand.
const RFC_COVERED = '{"a":"\u00e9","b":2}'; // the document writes b as 2.0
const PY_COVERED = '{"payload":{"a":"\u00e9","b":1.5,"big":12345678901234567890},"schema_version":1}';
const RESPONSES = '{"a":1}\n{"b":2}\n';

const schema = (name, body) => ({ $schema: "https://json-schema.org/draft/2020-12/schema", $id: `${ID}/${name}`, type: "object", additionalProperties: false, ...body });

function vector(pathName, expect, extra = {}) {
  const exit = { valid: 0, tampered: 1, invalid: 2 }[expect];
  return { path: pathName, expect, verify: { command: ["demo-verify", "{path}"], exit_code: exit }, note: `fixture ${expect}`, ...extra };
}

function manifest() {
  return {
    format: 1,
    package: "demo",
    vectors: [
      vector("valid/record.json", "valid", {
        documents: [{ path: ".", schema: "demo/schema/record.v3.json", schema_valid: true }],
        digests: [{ document: ".", value: "/input_sha256", covers: "/input", exclude: [], canonicalization: "rfc8785", canonical_file: "valid/record.input.canonical" }],
      }),
      vector("valid/legacy.json", "valid", {
        documents: [{ path: ".", schema: "demo/schema/legacy.v1.json", schema_valid: true }],
        digests: [{ document: ".", value: "/checksum", covers: "", exclude: ["checksum"], canonicalization: "python-json-v1", canonical_file: "valid/legacy.canonical" }],
      }),
      vector("valid/bundle", "valid", {
        documents: [{ path: "provenance.json", schema: "demo/schema/provenance.v1.json", schema_valid: true }],
        digests: [{ document: "provenance.json", value: "/files/responses.jsonl/sha256", canonicalization: "bytes", covers_file: "responses.jsonl" }],
      }),
      vector("tampered/record-edited.json", "tampered", {
        documents: [{ path: ".", schema: "demo/schema/record.v3.json", schema_valid: true }],
      }),
      vector("invalid/record-extra-member.json", "invalid", {
        documents: [{ path: ".", schema: "demo/schema/record.v3.json", schema_valid: false }],
      }),
      vector("invalid/record-duplicate-key.json", "invalid"),
    ],
  };
}

const FILES = {
  "ai-workflows/demo/demo/schema/record.v3.json": JSON.stringify(schema("record.v3.json", {
    required: ["schema_version", "input", "input_sha256"],
    properties: { schema_version: { const: 3 }, input: { type: "object" }, input_sha256: { type: "string", pattern: "^[0-9a-f]{64}$" } },
  })),
  "ai-workflows/demo/demo/schema/legacy.v1.json": JSON.stringify(schema("legacy.v1.json", {
    required: ["schema_version", "payload", "checksum"],
    properties: { schema_version: { const: 1 }, payload: { type: "object" }, checksum: { type: "string", pattern: "^[0-9a-f]{64}$" } },
  })),
  "ai-workflows/demo/demo/schema/provenance.v1.json": JSON.stringify(schema("provenance.v1.json", {
    required: ["files"],
    properties: { files: { type: "object" } },
  })),
  "ai-workflows/demo/conformance/valid/record.json": `{"schema_version":3,"input":{"b":2.0,"a":"\u00e9"},"input_sha256":"${sha(RFC_COVERED)}"}`,
  "ai-workflows/demo/conformance/valid/record.input.canonical": RFC_COVERED,
  "ai-workflows/demo/conformance/valid/legacy.json": `{"checksum":"${sha(PY_COVERED)}","schema_version":1,"payload":{"b":1.5,"a":"\u00e9","big":12345678901234567890}}`,
  "ai-workflows/demo/conformance/valid/legacy.canonical": PY_COVERED,
  "ai-workflows/demo/conformance/valid/bundle/responses.jsonl": RESPONSES,
  "ai-workflows/demo/conformance/valid/bundle/provenance.json": `{"files":{"responses.jsonl":{"sha256":"${sha(RESPONSES)}"}}}`,
  // Edited after digesting: the recorded digest no longer matches. Not recomputed by the checker.
  "ai-workflows/demo/conformance/tampered/record-edited.json": `{"schema_version":3,"input":{"b":3,"a":"\u00e9"},"input_sha256":"${sha(RFC_COVERED)}"}`,
  "ai-workflows/demo/conformance/invalid/record-extra-member.json": `{"schema_version":3,"input":{},"input_sha256":"${WRONG}","extra":true}`,
  "ai-workflows/demo/conformance/invalid/record-duplicate-key.json": `{"schema_version":3,"input":{},"input":{"a":1},"input_sha256":"${WRONG}"}`,
};

let root;
const file = (relative) => path.join(root, "ai-workflows/demo", relative);
const read = (relative) => readFileSync(file(relative), "utf8");
function write(relative, text) {
  mkdirSync(path.dirname(file(relative)), { recursive: true });
  writeFileSync(file(relative), text);
}
const editManifest = (change) => {
  const value = JSON.parse(read("conformance/manifest.json"));
  change(value);
  write("conformance/manifest.json", JSON.stringify(value, null, 2));
};
const check = () => checkRepository(root);
const failureText = (result) => result.failures.join("\n");

before(() => {
  root = mkdtempSync(path.join(tmpdir(), "conformance-"));
});
after(() => rmSync(root, { recursive: true, force: true }));
beforeEach(() => {
  rmSync(path.join(root, "ai-workflows"), { recursive: true, force: true });
  for (const [name, text] of Object.entries(FILES)) write(path.relative("ai-workflows/demo", name), text);
  write("conformance/manifest.json", JSON.stringify(manifest(), null, 2));
});

describe("a valid tree", () => {
  test("passes and recomputes every digest of every valid vector", async () => {
    const lines = [];
    const result = await checkRepository(root, (line) => lines.push(line));
    assert.deepEqual(result.failures, []);
    assert.equal(result.manifests, 1);
    assert.equal(result.vectors, 6);
    const output = lines.join("\n");
    assert.match(output, /ok\s+digest\s+\.#\/input_sha256 \(rfc8785\)/);
    assert.match(output, /ok\s+digest\s+\.#\/checksum \(python-json-v1\)/);
    assert.match(output, /ok\s+digest\s+provenance\.json#\/files\/responses\.jsonl\/sha256 \(bytes\)/);
    assert.match(output, /invalid as declared/);
  });

  test("a repository without manifests has nothing to check", async () => {
    rmSync(path.join(root, "ai-workflows"), { recursive: true });
    assert.deepEqual(await check(), { manifests: 0, vectors: 0, checks: 0, failures: [] });
  });
});

describe("rfc8785 digests", () => {
  test("a wrong recorded digest fails", async () => {
    write("conformance/valid/record.json", read("conformance/valid/record.json").replace(sha(RFC_COVERED), WRONG));
    const result = await check();
    assert.equal(result.failures.length, 1);
    assert.match(failureText(result), /valid\/record\.json: digest: \.#\/input_sha256 \(rfc8785\): recorded 0{64}, recomputed [0-9a-f]{64}/);
  });

  test("a covered value edited after digesting fails", async () => {
    write("conformance/valid/record.json", read("conformance/valid/record.json").replace('"b":2.0', '"b":2.5'));
    assert.match(failureText(await check()), /not the RFC 8785 form .*first difference at byte/);
  });

  test("a canonical file that is not canonical fails", async () => {
    for (const bytes of ['{"b":2,"a":"\u00e9"}', '{"a": "\u00e9","b":2}', `${RFC_COVERED}\n`, '{"a":"\\u00e9","b":2}']) {
      write("conformance/valid/record.input.canonical", bytes);
      const result = await check();
      assert.match(failureText(result), /record\.input\.canonical is not the RFC 8785 form/, JSON.stringify(bytes));
    }
  });

  test("an integer outside the I-JSON range fails", async () => {
    write("conformance/valid/record.json", read("conformance/valid/record.json").replace('"b":2.0', '"b":9007199254740993'));
    assert.match(failureText(await check()), /outside the I-JSON range/);
  });

  test("a duplicate key in a valid document fails", async () => {
    write("conformance/valid/record.json", read("conformance/valid/record.json").replace('"input":{', '"input":{"a":1,'));
    assert.match(failureText(await check()), /duplicate object key "a"/);
  });

  test("a missing canonical file, bad pointer or digest shape fails", async () => {
    rmSync(file("conformance/valid/record.input.canonical"));
    assert.match(failureText(await check()), /ENOENT/);
    write("conformance/valid/record.input.canonical", RFC_COVERED);
    editManifest((value) => { value.vectors[0].digests[0].covers = "/missing"; });
    assert.match(failureText(await check()), /no member "missing"/);
    editManifest((value) => { value.vectors[0].digests[0].covers = "/input"; value.vectors[0].digests[0].value = "/schema_version"; });
    assert.match(failureText(await check()), /not a 64-character lowercase hex digest/);
  });

  test("exclude needs a real JSON object, and pointers cannot enter a number", async () => {
    // /input/b is a number (written 2.0 in the document); /payload/b is one in the python-json-v1 vector.
    const probes = [
      [0, "/input/b", ["text"], /exclude needs the covered value to be an object/],
      [0, "/input/b/text", [], /no member "text"/],
      [0, "/input/b/0", [], /no member "0"|no array element/],
      [0, "/input/a", ["length"], /exclude needs/],
      [0, "/input_sha256", ["length"], /exclude needs/],
      [1, "/payload/b", ["text"], /exclude needs the covered value to be an object/],
      [1, "/payload/b/text", [], /no member "text"/],
      [1, "/payload/big", ["text"], /exclude needs/],
      [1, "/payload/b/text", ["text"], /no member "text"/],
    ];
    for (const [index, covers, exclude, expected] of probes) {
      write("conformance/manifest.json", JSON.stringify(manifest(), null, 2)); // one broken digest at a time
      editManifest((value) => { Object.assign(value.vectors[index].digests[0], { covers, exclude }); });
      assert.match(failureText(await check()), expected, `${covers} ${JSON.stringify(exclude)}`);
    }
  });

  test("excluding a member that is absent fails", async () => {
    editManifest((value) => { value.vectors[0].digests[0].exclude = ["nope"]; });
    assert.match(failureText(await check()), /excluded member "nope"/);
  });
});

describe("python-json-v1 digests", () => {
  test("a wrong recorded digest fails", async () => {
    write("conformance/valid/legacy.json", read("conformance/valid/legacy.json").replace(sha(PY_COVERED), WRONG));
    assert.match(failureText(await check()), /\.#\/checksum \(python-json-v1\): recorded 0{64}/);
  });

  test("a canonical file that is not the covered value fails", async () => {
    write("conformance/valid/legacy.canonical", PY_COVERED.replace("1.5", "1.25"));
    assert.match(failureText(await check()), /is not the python-json-v1 form/);
  });

  test("a canonical file in another form fails even when the value and digest agree", async () => {
    const reordered = '{"schema_version":1,"payload":{"a":"\u00e9","b":1.5,"big":12345678901234567890}}';
    write("conformance/valid/legacy.canonical", reordered);
    write("conformance/valid/legacy.json", read("conformance/valid/legacy.json").replace(sha(PY_COVERED), sha(reordered)));
    assert.match(failureText(await check()), /is not the python-json-v1 form/);
    const spaced = PY_COVERED.replace('"payload":', '"payload": ');
    write("conformance/valid/legacy.canonical", spaced);
    write("conformance/valid/legacy.json", read("conformance/valid/legacy.json").replace(sha(reordered), sha(spaced)));
    assert.match(failureText(await check()), /is not the python-json-v1 form/);
  });

  test("int 0, float 0.0 and float -0.0 are different values even when the digest is resealed", async () => {
    // The document and canonical file agree on the digest but disagree on the number token.
    const withZero = (documentZero, canonicalZero) => {
      const canonical = `{"payload":{"a":"\u00e9","b":1.5,"big":12345678901234567890,"z":${canonicalZero}},"schema_version":1}`;
      write("conformance/valid/legacy.canonical", canonical);
      write("conformance/valid/legacy.json",
        `{"checksum":"${sha(canonical)}","schema_version":1,"payload":{"z":${documentZero},"b":1.5,"a":"\u00e9","big":12345678901234567890}}`);
    };
    withZero("0.0", "0.0");
    assert.deepEqual((await check()).failures, [], "agreeing tokens pass");
    for (const [documentZero, canonicalZero] of [["0.0", "0"], ["0", "0.0"], ["-0.0", "0.0"], ["0.0", "-0.0"], ["1", "1.0"], ["1.0", "1"]]) {
      withZero(documentZero, canonicalZero);
      assert.match(failureText(await check()), /is not the python-json-v1 form/, `${documentZero} vs ${canonicalZero}`);
    }
    withZero("-0.0", "-0.0");
    assert.deepEqual((await check()).failures, [], "-0.0 is kept");
  });

  test("a number written with a trailing zero fails even when the digest is resealed", async () => {
    // 1.50 is the same value as 1.5 but not Python's spelling, so Python would write different bytes.
    for (const [from, to] of [["1.5", "1.50"], ["1.5", "15e-1"], ["1.5", "1.5e0"]]) {
      const spelled = PY_COVERED.replace(from, to);
      write("conformance/valid/legacy.canonical", spelled);
      write("conformance/valid/legacy.json",
        `{"checksum":"${sha(spelled)}","schema_version":1,"payload":{"b":${to},"a":"\u00e9","big":12345678901234567890}}`);
      assert.match(failureText(await check()), /is not the python-json-v1 form/, to);
    }
  });

  test("a digest that does not match the canonical file fails", async () => {
    write("conformance/valid/legacy.json", read("conformance/valid/legacy.json").replace('"b":1.5', '"b":1.5,"added":1'));
    assert.match(failureText(await check()), /is not the python-json-v1 form/);
  });
});

describe("bytes digests", () => {
  test("an edited covered file fails", async () => {
    write("conformance/valid/bundle/responses.jsonl", `${RESPONSES}{"c":3}\n`);
    assert.match(failureText(await check()), /provenance\.json#\/files\/responses\.jsonl\/sha256 \(bytes\): recorded [0-9a-f]{64}, recomputed [0-9a-f]{64}/);
  });

  test("line endings count", async () => {
    write("conformance/valid/bundle/responses.jsonl", RESPONSES.replaceAll("\n", "\r\n"));
    assert.equal((await check()).failures.length, 1);
  });
});

describe("schema validation", () => {
  test("a violation in a document declared valid fails", async () => {
    write("conformance/valid/record.json", read("conformance/valid/record.json").replace('"schema_version":3', '"schema_version":3,"extra":1'));
    assert.match(failureText(await check()), /schema: \. against demo\/schema\/record\.v3\.json: declared schema_valid=true but \/ must NOT have additional properties/);
  });

  test("a document declared invalid that validates fails", async () => {
    write("conformance/invalid/record-extra-member.json", `{"schema_version":3,"input":{},"input_sha256":"${WRONG}"}`);
    assert.match(failureText(await check()), /declared schema_valid=false but the document validates/);
  });

  test("an unparseable document is not schema valid", async () => {
    write("conformance/valid/record.json", "{");
    assert.match(failureText(await check()), /declared schema_valid=true but is not parseable JSON/);
  });

  test("a document declared invalid must still exist as a file", async () => {
    write("conformance/invalid/bundle/record.json", `{"schema_version":3,"input":{},"input_sha256":"${WRONG}","extra":true}`);
    for (const [documentPath, code] of [["missing.json", /ENOENT/], [".", /EISDIR/]]) {
      editManifest((value) => {
        value.vectors = value.vectors.filter((item) => item.path !== "invalid/bundle");
        value.vectors.push(vector("invalid/bundle", "invalid", {
          documents: [{ path: documentPath, schema: "demo/schema/record.v3.json", schema_valid: false }],
        }));
      });
      const text = failureText(await check());
      assert.match(text, /invalid\/bundle: schema: /, documentPath);
      assert.match(text, code, documentPath);
    }
  });

  test("an unreferenced schema that is malformed, id-less or invalid fails", async () => {
    for (const [text, expected] of [
      ["{", /unused\.v1\.json cannot be loaded: .*JSON/],
      ['{"type":"object"}', /unused\.v1\.json cannot be loaded: schema has no string \$id/],
      [JSON.stringify(schema("unused.v1.json", { typo_keyword: 1 })), /unused\.v1\.json cannot be loaded: .*unknown keyword/],
      [JSON.stringify(schema("unused.v1.json", { type: "nonsense" })), /unused\.v1\.json cannot be loaded/],
      [JSON.stringify(schema("record.v3.json", {})), /unused\.v1\.json cannot be loaded: .*already exists/],
    ]) {
      write("demo/schema/unused.v1.json", text);
      assert.match(failureText(await check()), expected, text);
    }
    write("demo/schema/unused.v1.json", JSON.stringify(schema("unused.v1.json", {})));
    assert.deepEqual((await check()).failures, []);
  });

  test("a missing, id-less or invalid schema fails", async () => {
    rmSync(file("demo/schema/record.v3.json"));
    assert.match(failureText(await check()), /ENOENT/);
    write("demo/schema/record.v3.json", '{"type":"object"}');
    assert.match(failureText(await check()), /no string \$id/);
    write("demo/schema/record.v3.json", JSON.stringify(schema("record.v3.json", { typo_keyword: 1 })));
    assert.match(failureText(await check()), /unknown keyword/);
  });
});

describe("manifest rules", () => {
  test("an exit code that disagrees with expect is rejected", async () => {
    editManifest((value) => { value.vectors[0].verify.exit_code = 1; });
    assert.match(failureText(await check()), /manifest: does not match manifest\.schema\.json/);
  });

  test("a valid vector without digests is rejected", async () => {
    editManifest((value) => { delete value.vectors[0].digests; });
    assert.match(failureText(await check()), /does not match manifest\.schema\.json/);
  });

  test("a valid vector must declare documents", async () => {
    editManifest((value) => { delete value.vectors[0].documents; });
    assert.match(failureText(await check()), /does not match manifest\.schema\.json/);
    editManifest((value) => { value.vectors[0].documents = []; });
    assert.match(failureText(await check()), /does not match manifest\.schema\.json/);
  });

  test("every digest document needs a schema-validated documents entry", async () => {
    write("conformance/valid/bundle/extra.json", '{"files":{}}');
    editManifest((value) => {
      value.vectors[2].documents = [{ path: "extra.json", schema: "demo/schema/provenance.v1.json", schema_valid: true }];
    });
    assert.match(failureText(await check()), /provenance\.json#\/files\/responses\.jsonl\/sha256: document has no schema-validated entry in documents/);
  });

  test("paths cannot leave the vector tree", async () => {
    editManifest((value) => { value.vectors[0].path = "valid/../../outside.json"; });
    assert.match(failureText(await check()), /does not match manifest\.schema\.json/);
  });

  test("a vector must live under the directory named by its expectation", async () => {
    editManifest((value) => { value.vectors[0].expect = "tampered"; value.vectors[0].verify.exit_code = 1; });
    assert.match(failureText(await check()), /a tampered vector must live under tampered\//);
  });

  test("a file vector only allows '.' as its document", async () => {
    editManifest((value) => { value.vectors[0].documents[0].path = "other.json"; });
    assert.match(failureText(await check()), /must be "\." for a file vector/);
  });

  test("a vector file missing from disk fails", async () => {
    rmSync(file("conformance/tampered/record-edited.json"));
    assert.match(failureText(await check()), /vector path does not exist/);
  });

  test("a file no vector references fails", async () => {
    write("conformance/valid/stray.json", "{}");
    assert.match(failureText(await check()), /valid\/stray\.json is not referenced by any vector/);
  });

  test("a manifest that is not strict JSON fails", async () => {
    write("conformance/manifest.json", '{"format":1,"format":1}');
    assert.match(failureText(await check()), /duplicate object key "format"/);
  });
});

describe("command line", () => {
  test("exits 0 with a summary when everything agrees and 1 with the failing digest otherwise", async () => {
    const ok = await run(process.execPath, [VERIFY, root]);
    assert.match(ok.stdout, /conformance OK: 1 manifests, 6 vectors/);
    write("conformance/valid/record.json", read("conformance/valid/record.json").replace(sha(RFC_COVERED), WRONG));
    await assert.rejects(run(process.execPath, [VERIFY, root]), (error) => {
      assert.equal(error.code, 1);
      assert.match(error.stdout, /FAIL\s+digest/);
      assert.match(error.stderr, /conformance FAILED: 1 manifests, 6 vectors, \d+ checks, 1 failures/);
      return true;
    });
  });

  test("with no manifests it succeeds and says so", async () => {
    rmSync(path.join(root, "ai-workflows"), { recursive: true });
    const result = await run(process.execPath, [VERIFY, root]);
    assert.match(result.stdout, /0 manifests found/);
  });

  test("usage errors exit 2", async () => {
    await assert.rejects(run(process.execPath, [VERIFY, root, "extra"]), (error) => error.code === 2);
  });
});
