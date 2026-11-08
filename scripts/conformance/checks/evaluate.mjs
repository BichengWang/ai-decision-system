// Offline evaluation of the conformance vectors against the package verifiers.
//
// The verifiers run as black boxes: each vector's manifest `verify.command`, with its console
// script taken from one directory (a venv's bin/). Nothing here imports Python code, so this
// component stays inside its import boundary (scripts/workspace.py check).
//
//   (a) vector counts per project and kind;
//   (b) a "hash + JSON Schema" baseline (Ajv plus digest recomputation, no replay) against each
//       verifier's exit code;
//   (c) a single-leaf mutation sweep over every valid vector in two modes: stale (digests kept)
//       and resealed (every digest the manifest declares for the vector recomputed);
//   (d) record sizes and, when asked, CLI verify latency (median of N runs).
//
// Everything but latency is deterministic: fixed ordering, no randomness, no clock.

import { execFile, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { constants as fsConstants, promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { CanonicalizationError, canonicalizeRfc8785, pythonFloatRepr, serializePythonJsonV1 } from "./canonical.mjs";
import { contained, discoverManifests, loadProjectSchemas, MANIFEST_SCHEMA_PATH, newAjv, withoutMembers } from "./conformance.mjs";
import { decodeUtf8, parseJson, RawNumber, rawNumber, readNumber, resolvePointer } from "./json.mjs";

export const MODES = ["stale", "resealed"];
const KINDS = ["valid", "tampered", "invalid"];
const BASELINES = ["strict", "json_parse"];
const TRACEBACK = "Traceback (most recent call last)";
const INTEGER_LITERAL = /^-?(?:0|[1-9][0-9]*)$/;
const EXTERNAL_TOOLS = ["opa", "cedar", "cosign"];
const run = promisify(execFile);

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const slash = (file) => file.split(path.sep).join("/");
const byText = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
const percent = (part, whole) => (whole === 0 ? null : Math.round((1000 * part) / whole) / 10);

export class UsageError extends Error {}

// ---------------------------------------------------------------------------------------------
// Vectors

function recordType(vector, isDirectory) {
  const first = vector.documents?.[0];
  if (!first) return "unknown";
  return isDirectory ? `${path.basename(first.path, ".json")}-dir` : path.basename(first.schema, ".json");
}

/** Every manifest under root (validated against manifest.schema.json) and its vectors, in manifest order. */
export async function loadVectors(root) {
  const validateManifest = newAjv().compile(JSON.parse(await fs.readFile(MANIFEST_SCHEMA_PATH, "utf8")));
  const manifests = [];
  const vectors = [];
  for (const file of await discoverManifests(root)) {
    const bytes = await fs.readFile(file);
    const manifest = parseJson(decodeUtf8(bytes));
    const label = slash(path.relative(root, file));
    if (!validateManifest(manifest)) throw new UsageError(`${label} does not match manifest.schema.json; run node verify.mjs`);
    const conformanceDir = path.dirname(file);
    const projectDir = path.dirname(conformanceDir);
    const project = path.basename(projectDir);
    manifests.push({ path: label, project, package: manifest.package, vectors: manifest.vectors.length, sha256: sha256(bytes) });
    for (const spec of manifest.vectors) {
      const abs = contained(conformanceDir, spec.path, "path");
      const isDirectory = (await fs.stat(abs)).isDirectory();
      vectors.push({ project, package: manifest.package, projectDir, path: spec.path, expect: spec.expect, abs, isDirectory, type: recordType(spec, isDirectory), spec });
    }
  }
  return { manifests, vectors };
}

async function sizeOf(file) {
  const stat = await fs.stat(file);
  if (!stat.isDirectory()) return stat.size;
  let total = 0;
  for (const entry of await fs.readdir(file)) total += await sizeOf(path.join(file, entry));
  return total;
}

// ---------------------------------------------------------------------------------------------
// Running verifiers

/** Child environment: PATH is --bin then /usr/bin:/bin (or the caller's PATH); no other variables leak in. */
export function verifierEnvironment(bin, { inheritPath = false, home } = {}) {
  const rest = inheritPath ? (process.env.PATH ?? "").split(path.delimiter).filter(Boolean) : ["/usr/bin", "/bin"];
  return { PATH: [bin, ...rest].join(path.delimiter), HOME: home, TZ: "UTC", PYTHONUTF8: "1", PYTHONDONTWRITEBYTECODE: "1" };
}

/** Run argv; resolves { code, crashed } where crashed means a Python traceback on stderr. */
export function runProcess(argv, { env, cwd, timeoutMs = 120_000 }) {
  return new Promise((resolve) => {
    let settled = false;
    let stderr = "";
    let timer;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    const child = spawn(argv[0], argv.slice(1), { env, cwd, stdio: ["ignore", "ignore", "pipe"] });
    timer = setTimeout(() => child.kill("SIGKILL"), timeoutMs);
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => {
      if (stderr.length < 65_536) stderr += chunk;
    });
    child.on("error", (error) => finish({ code: null, crashed: false, error: error.message }));
    child.on("close", (code) => finish({ code, crashed: stderr.includes(TRACEBACK) }));
  });
}

// A run with no exit code was killed (timeout, a machine that slept through the timeout) or never
// started. It says nothing about the record, so it is retried, and a run that never yields an exit
// code is an error, not a detection.
const ATTEMPTS = 3;

export async function runVerifier(argv, options) {
  let result;
  for (let attempt = 1; attempt <= ATTEMPTS; attempt += 1) {
    result = await runProcess(argv, options);
    if (result.code !== null) break;
  }
  return result;
}

function commandFor(vector, target, bin) {
  const [name, ...args] = vector.spec.verify.command;
  return [path.join(bin, name), ...args.map((arg) => (arg === "{path}" ? target : arg))];
}

async function checkBin(vectors, bin) {
  const missing = [];
  for (const name of [...new Set(vectors.map((vector) => vector.spec.verify.command[0]))].sort()) {
    await fs.access(path.join(bin, name), fsConstants.X_OK).catch(() => missing.push(name));
  }
  if (missing.length > 0) {
    throw new UsageError(`--bin ${bin} has no executable ${missing.join(", ")}; install the three packages from this checkout into that venv`);
  }
}

async function pool(items, jobs, worker) {
  const results = new Array(items.length);
  let next = 0;
  const lane = async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await worker(items[index], index);
    }
  };
  await Promise.all(Array.from({ length: Math.max(1, jobs) }, lane));
  return results;
}

// ---------------------------------------------------------------------------------------------
// (b) Hash + JSON Schema baseline

function lookup(document, pointer) {
  try {
    return resolvePointer(document, pointer);
  } catch (error) {
    if (error instanceof RangeError) return undefined;
    throw error;
  }
}

/** JS numbers for RFC 8785: a RawNumber becomes a number, or a BigInt outside the safe range. */
function plainNumbers(value) {
  if (value instanceof RawNumber) return readNumber(value.text);
  if (Array.isArray(value)) return value.map(plainNumbers);
  if (value === null || typeof value !== "object") return value;
  const copy = {};
  for (const key of Object.keys(value)) Object.defineProperty(copy, key, { value: plainNumbers(value[key]), enumerable: true, writable: true, configurable: true });
  return copy;
}

function canonicalBytes(value, canonicalization) {
  return canonicalization === "python-json-v1" ? serializePythonJsonV1(value) : canonicalizeRfc8785(plainNumbers(value));
}

// Where each schema's records carry a digest of what, learned from the valid vectors: what a
// checker knows that has the schemas and the digest rules but no replay.
function digestSpecs(vectors) {
  const specs = new Map();
  for (const vector of vectors.filter((item) => item.expect === "valid")) {
    const schemaOf = new Map((vector.spec.documents ?? []).map((document) => [document.path, document.schema]));
    for (const { document, canonical_file: _canonical, ...spec } of vector.spec.digests ?? []) {
      const key = `${vector.project}\0${schemaOf.get(document)}`;
      if (!specs.has(key)) specs.set(key, new Map());
      specs.get(key).set(JSON.stringify(spec), spec);
    }
  }
  return specs;
}

// Digests a verifier checks that the manifests' `digests` entries do not declare, found by reading
// the verifiers. Every run also scans the valid vectors for other 64-hex values and reports any it
// cannot account for as a problem (unaccountedDigests), so a new one cannot go unnoticed.
//   derive      the digest is the RFC 8785 SHA-256 of a value built from the same document;
//   covers_file the digest is the SHA-256 of another file of a directory vector;
//   neither     it covers files no edit here touches (and only replay knows which), so it is never
//               recomputed, never mutated, and not checked by the baseline.
const cedarProposal = (document) => {
  // decision-control adapters/_binding.py: the document a frozen Cedar decision is bound to.
  const record = document?.record;
  return { action: record?.recommendation?.action, proposed_by: record?.proposed_by, ticket: record?.ticket, recommendation: record?.recommendation };
};

export const EMBEDDED_DIGESTS = {
  "decision-control": [
    { document: ".", value: "/record/external_policy/request/context/proposal_sha256", what: "RFC 8785 SHA-256 of the proposal a Cedar decision is bound to", derive: cedarProposal },
  ],
  "jev-decision": [
    { document: "evaluation.json", value: "/calibration/sha256", what: "SHA-256 of calibration.json", covers_file: "calibration.json" },
    { document: "calibration.json", value: "/fitted_on/cases_sha256", what: "SHA-256 of the fitting run's cases.jsonl" },
    { document: "calibration.json", value: "/fitted_on/responses_sha256", what: "SHA-256 of the fitting run's responses.jsonl" },
  ],
};

const SHA256_HEX = /^[0-9a-f]{64}$/;
const present = (value) => value !== undefined && value !== null;
const schemaVersionOf = (vector) => {
  const match = /^(.*)\.v(\d+)\.json$/.exec(path.basename(vector.spec.documents?.[0]?.schema ?? ""));
  return match ? { family: match[1], version: Number(match[2]) } : null;
};

/** Which canonical form each schema version uses for each declared digest, learned from the valid vectors. */
export function canonicalForms(vectors) {
  const forms = new Map();
  for (const vector of vectors.filter((item) => item.expect === "valid" && !item.isDirectory)) {
    const schema = schemaVersionOf(vector);
    if (schema === null) continue;
    for (const digest of (vector.spec.digests ?? []).filter((item) => item.canonicalization !== "bytes")) {
      const key = `${vector.project}\0${schema.family}\0${digest.value}`;
      if (!forms.has(key)) forms.set(key, new Map());
      const known = forms.get(key).get(schema.version);
      if (known !== undefined && known !== digest.canonicalization) {
        throw new Error(`${vector.project} ${schema.family}.v${schema.version} ${digest.value}: valid vectors disagree on the canonical form`);
      }
      forms.get(key).set(schema.version, digest.canonicalization);
    }
  }
  return forms;
}

/** The shallowest `schema_version` leaf holding the schema file's version, or null. */
function versionTokens(document, version) {
  const candidates = leafPaths(document).filter((tokens) => {
    const value = lookup(document, toPointer(tokens));
    return tokens[tokens.length - 1] === "schema_version" && value instanceof RawNumber && value.text === String(version);
  });
  return candidates.sort((a, b) => a.length - b.length)[0] ?? null;
}

/** 64-hex values in valid vectors that are neither a declared digest nor in EMBEDDED_DIGESTS. */
export async function unaccountedDigests(valid, embedded = EMBEDDED_DIGESTS) {
  const found = [];
  for (const vector of valid) {
    const accounted = new Set([...(vector.spec.digests ?? []), ...(embedded[vector.project] ?? [])].map((digest) => `${digest.document}\0${digest.value}`));
    const names = vector.isDirectory ? (await fs.readdir(vector.abs)).filter((name) => name.endsWith(".json")).sort(byText) : ["."];
    for (const name of names) {
      const document = parseJson(decodeUtf8(await fs.readFile(name === "." ? vector.abs : path.join(vector.abs, name))));
      for (const tokens of leafPaths(document)) {
        const value = lookup(document, toPointer(tokens));
        if (typeof value === "string" && SHA256_HEX.test(value) && !accounted.has(`${name}\0${toPointer(tokens)}`)) {
          found.push(`${vector.project}/${vector.path}${name === "." ? "" : `/${name}`}#${toPointer(tokens)}`);
        }
      }
    }
  }
  return found;
}

async function embeddedProblem(rule, text, base, parse) {
  if (!rule.derive && !rule.covers_file) return null; // covers files only replay can identify
  const document = parse(text);
  const recorded = lookup(document, rule.value);
  if (!present(recorded)) return null;
  if (rule.covers_file) {
    const bytes = await fs.readFile(contained(base, rule.covers_file, "covers_file")).catch(() => null);
    if (bytes === null) return `${rule.covers_file} is missing`;
    return sha256(bytes) === recorded ? null : `SHA-256 of ${rule.covers_file} differs`;
  }
  try {
    return sha256(canonicalBytes(rule.derive(document), "rfc8785")) === recorded ? null : "differs";
  } catch (error) {
    return error.message;
  }
}

async function digestProblem(spec, text, base, parse) {
  const legacy = spec.canonicalization === "python-json-v1";
  const document = parse(text, legacy ? { number: rawNumber } : {});
  const recorded = lookup(document, spec.value);
  if (spec.canonicalization === "bytes") {
    if (recorded === undefined || recorded === null) return null; // this record has no such file
    const bytes = await fs.readFile(contained(base, spec.covers_file, "covers_file")).catch(() => null);
    if (bytes === null) return `${spec.covers_file} is missing`;
    return sha256(bytes) === recorded ? null : `SHA-256 of ${spec.covers_file} differs`;
  }
  const covered = lookup(document, spec.covers);
  if ((recorded === undefined || recorded === null) && (covered === undefined || covered === null)) return null;
  if (covered === undefined) return `${spec.covers || "the document"} is missing`;
  try {
    return sha256(canonicalBytes(withoutMembers(covered, spec.exclude ?? []), spec.canonicalization)) === recorded ? null : "differs";
  } catch (error) {
    return error.message;
  }
}

/** Reasons the baseline rejects a vector; empty means accepted. */
async function baselineReasons(vector, mode, { specs, schemasFor, embedded }) {
  const parse = (text, options = {}) => parseJson(text, mode === "strict" ? options : { ...options, duplicates: "last" });
  const documents = vector.spec.documents ?? [];
  const reasons = [];
  if (documents.length === 0) {
    if (!vector.isDirectory) {
      try {
        parse(decodeUtf8(await fs.readFile(vector.abs)));
      } catch {
        reasons.push("not parseable JSON");
      }
    }
    return reasons;
  }
  const base = vector.isDirectory ? vector.abs : path.dirname(vector.abs);
  const schemas = await schemasFor(vector);
  for (const document of documents) {
    const where = document.path === "." ? "" : `${document.path}: `;
    let text;
    try {
      text = decodeUtf8(await fs.readFile(vector.isDirectory ? contained(vector.abs, document.path, "document path") : vector.abs));
      // Schema validation reads documents with JSON.parse, as verify.mjs does; strict mode also needs strict JSON.
      const data = JSON.parse(text);
      if (mode === "strict") parse(text);
      const validate = await schemas.validatorFor(contained(vector.projectDir, document.schema, "schema"));
      if (!validate(data)) reasons.push(`${where}schema`);
    } catch (error) {
      reasons.push(`${where}not parseable JSON (${error.message})`);
      continue;
    }
    for (const spec of specs.get(`${vector.project}\0${document.schema}`)?.values() ?? []) {
      const problem = await digestProblem(spec, text, base, parse);
      if (problem !== null) reasons.push(`${where}digest ${spec.value}: ${problem}`);
    }
    for (const rule of (embedded[vector.project] ?? []).filter((item) => item.document === document.path)) {
      const problem = await embeddedProblem(rule, text, base, parse);
      if (problem !== null) reasons.push(`${where}digest ${rule.value}: ${problem}`);
    }
  }
  return reasons;
}

// ---------------------------------------------------------------------------------------------
// (c) Single-leaf mutations

const escapeToken = (token) => token.replaceAll("~", "~0").replaceAll("/", "~1");
const toPointer = (tokens) => tokens.map((token) => `/${escapeToken(token)}`).join("");
const pointerTokens = (pointer) => (pointer === "" ? [] : pointer.slice(1).split("/").map((token) => token.replaceAll("~1", "/").replaceAll("~0", "~")));
/** A field name for reports: array indices become []. */
export const generalize = (pointer) => pointer.replace(/\/\d+(?=\/|$)/g, "/[]");

function leafPaths(node, tokens = [], out = []) {
  if (node !== null && typeof node === "object" && !(node instanceof RawNumber)) {
    // Empty objects and arrays have no leaf, as in the prototype sweep.
    const keys = Array.isArray(node) ? node.map((_, index) => String(index)) : Object.keys(node);
    for (const key of keys) leafPaths(node[key], [...tokens, key], out);
  } else {
    out.push(tokens);
  }
  return out;
}

/** Replace the value at tokens; returns a function that restores the old value. */
function replaceAt(document, tokens, value) {
  let parent = document;
  for (const token of tokens.slice(0, -1)) parent = parent[token];
  const key = tokens[tokens.length - 1];
  const old = parent[key];
  parent[key] = value;
  return () => {
    parent[key] = old;
  };
}

/** One edit per JSON type: integer +1, float +0.125 (x2 when |x| >= 1e6), string + "x", boolean flipped, null to "x". */
export function mutateValue(value) {
  if (typeof value === "boolean") return !value;
  if (value === null) return "x";
  if (typeof value === "string") return `${value}x`;
  if (value instanceof RawNumber) {
    if (INTEGER_LITERAL.test(value.text)) return new RawNumber((BigInt(value.text) + 1n).toString());
    const number = Number(value.text);
    return new RawNumber(pythonFloatRepr(Math.abs(number) < 1e6 ? number + 0.125 : number * 2));
  }
  throw new TypeError(`cannot mutate ${typeof value}`);
}

function splitTrailingNewlines(bytes) {
  let end = bytes.length;
  while (end > 0 && bytes[end - 1] === 0x0a) end -= 1;
  return { body: bytes.subarray(0, end), tail: bytes.subarray(end) };
}

// Seal `covered` in `form`, or report that it has no such form: an edit can leave RFC 8785's range
// (an integer past 2^53-1), and then no one can reseal it; the digest stays stale and the run is
// reported as unsealable instead of being counted.
function seal(document, tokens, covered, form) {
  try {
    return replaceAt(document, tokens, sha256(canonicalBytes(covered, form)));
  } catch (error) {
    if (error instanceof CanonicalizationError) return null;
    throw error;
  }
}

// A file vector: every leaf except digests, declared or embedded. Written back in python-json-v1
// form, which keeps every integer an integer and every float a float for the Python readers.
// Resealing recomputes the embedded digests first (they sit inside what the declared ones cover),
// then the declared ones innermost first, each in the form the edited schema_version requires.
function fileTasks(vector, bytes, { forms, embedded }) {
  const document = parseJson(decodeUtf8(bytes), { number: rawNumber });
  const declared = vector.spec.digests ?? [];
  const derived = (embedded[vector.project] ?? []).filter((rule) => rule.document === "." && rule.derive && present(lookup(document, rule.value)));
  const digestLeaves = new Set([...declared, ...derived].map((digest) => digest.value));
  const order = [...declared].sort((a, b) => pointerTokens(b.value).length - pointerTokens(a.value).length);
  const schema = schemaVersionOf(vector);
  const versionAt = schema === null ? null : versionTokens(document, schema.version);
  const name = path.basename(vector.abs);
  const tasks = [{ vector, mode: "control", group: null, field: "", files: [[name, serializePythonJsonV1(document)]] }];
  for (const tokens of leafPaths(document)) {
    const field = toPointer(tokens);
    if (digestLeaves.has(field)) continue;
    for (const mode of MODES) {
      const undo = [replaceAt(document, tokens, mutateValue(lookup(document, field)))];
      let unsealable = false;
      if (mode === "resealed") {
        const edited = versionAt === null ? undefined : lookup(document, toPointer(versionAt));
        const version = edited instanceof RawNumber && INTEGER_LITERAL.test(edited.text) ? Number(edited.text) : undefined;
        const steps = [
          ...derived.map((rule) => [rule.value, () => rule.derive(document), "rfc8785"]),
          ...order.map((digest) => [digest.value, () => withoutMembers(resolvePointer(document, digest.covers), digest.exclude ?? []),
            forms.get(`${vector.project}\0${schema?.family}\0${digest.value}`)?.get(version) ?? digest.canonicalization]),
        ];
        for (const [pointer, covered, form] of steps) {
          const restore = seal(document, pointerTokens(pointer), covered(), form);
          if (restore === null) unsealable = true;
          else undo.push(restore);
        }
      }
      const written = serializePythonJsonV1(document);
      for (const restore of undo.reverse()) restore();
      tasks.push({ vector, mode, group: null, field, unsealable, files: [[name, written]] });
    }
  }
  return { tasks, digestLeaves: [...digestLeaves].filter((pointer) => derived.some((rule) => rule.value === pointer)).length };
}

// A directory vector: every leaf of each JSON file covered by a `bytes` digest, when the file is in
// compact sorted (python-json-v1) form so it can be rewritten as its producer writes it. Resealing
// rewrites every digest of an edited file: embedded ones in other files first (evaluation.json's
// SHA-256 of calibration.json), then the hashing document's (provenance.json, which is not mutated).
function directoryTasks(vector, files, skipped, { embedded }) {
  const byteDigests = (vector.spec.digests ?? []).filter((digest) => digest.canonicalization === "bytes");
  const hashing = [...new Set(byteDigests.map((digest) => digest.document))].sort(byText);
  const rules = (embedded[vector.project] ?? []).filter((rule) => rule.document !== "." && files.has(rule.document));
  const parsed = (raw) => parseJson(decodeUtf8(raw), { number: rawNumber });
  const rewrite = (raw, document) => Buffer.concat([serializePythonJsonV1(document), splitTrailingNewlines(raw).tail]);
  const reseal = (changed) => {
    for (let pass = 0; pass <= rules.length; pass += 1) {
      for (const rule of rules.filter((item) => item.covers_file && changed.has(item.covers_file))) {
        const raw = changed.get(rule.document) ?? files.get(rule.document);
        const document = parsed(raw);
        if (!present(lookup(document, rule.value))) continue;
        replaceAt(document, pointerTokens(rule.value), sha256(changed.get(rule.covers_file)));
        changed.set(rule.document, rewrite(raw, document));
      }
    }
    const hashes = hashing.map((name) => {
      const document = parsed(files.get(name));
      for (const digest of byteDigests) {
        if (digest.document === name && changed.has(digest.covers_file)) replaceAt(document, pointerTokens(digest.value), sha256(changed.get(digest.covers_file)));
      }
      return [name, rewrite(files.get(name), document)];
    });
    return [...changed.entries(), ...hashes];
  };
  const tasks = [{ vector, mode: "control", group: null, field: "", files: reseal(new Map()) }];
  let digestLeaves = 0;
  const targets = [...new Set(byteDigests.map((digest) => digest.covers_file))].filter((name) => !hashing.includes(name)).sort(byText);
  for (const name of targets) {
    if (!name.endsWith(".json")) continue;
    const { body, tail } = splitTrailingNewlines(files.get(name));
    const document = parseJson(decodeUtf8(body), { number: rawNumber });
    if (!serializePythonJsonV1(document).equals(body)) {
      skipped.push({ vector: `${vector.project}/${vector.path}`, file: name, reason: "not in compact sorted JSON form" });
      continue;
    }
    const own = new Set(rules.filter((rule) => rule.document === name).map((rule) => rule.value));
    for (const tokens of leafPaths(document)) {
      const field = toPointer(tokens);
      if (own.has(field)) {
        digestLeaves += 1;
        continue;
      }
      for (const mode of MODES) {
        const restore = replaceAt(document, tokens, mutateValue(lookup(document, field)));
        const written = Buffer.concat([serializePythonJsonV1(document), tail]);
        restore();
        const changed = mode === "resealed" ? reseal(new Map([[name, written]])) : [[name, written]];
        tasks.push({ vector, mode, group: name, field, unsealable: false, files: changed });
      }
    }
  }
  return { tasks, digestLeaves };
}

async function mutationTasks(valid, skipped, context) {
  const tasks = [];
  const digestLeaves = new Map();
  for (const vector of valid) {
    let made;
    if (vector.isDirectory) {
      const files = new Map();
      const names = [...(vector.spec.digests ?? []).flatMap((digest) => [digest.document, digest.covers_file]), ...(context.embedded[vector.project] ?? []).map((rule) => rule.document)];
      for (const name of names.filter((item) => item && item !== ".")) {
        if (!files.has(name)) {
          const bytes = await fs.readFile(contained(vector.abs, name, "file")).catch(() => null);
          if (bytes !== null) files.set(name, bytes);
        }
      }
      made = directoryTasks(vector, files, skipped, context);
    } else {
      made = fileTasks(vector, await fs.readFile(vector.abs), context);
    }
    tasks.push(...made.tasks);
    const key = `${vector.project}\0${vector.type}`;
    digestLeaves.set(key, (digestLeaves.get(key) ?? 0) + made.digestLeaves);
  }
  return { tasks, digestLeaves };
}

async function runTask(task, index, { tmp, bin, env }) {
  const dir = path.join(tmp, `task-${index}`);
  await fs.mkdir(dir);
  const target = path.join(dir, path.basename(task.vector.abs));
  if (task.vector.isDirectory) {
    await fs.cp(task.vector.abs, target, { recursive: true });
    for (const [name, bytes] of task.files) await fs.writeFile(contained(target, name, "file"), bytes);
  } else {
    await fs.writeFile(target, task.files[0][1]);
  }
  const result = await runVerifier(commandFor(task.vector, target, bin), { env, cwd: dir });
  await fs.rm(dir, { recursive: true, force: true });
  return { code: result.code, crashed: result.crashed };
}

const emptyMode = () => ({ mutations: 0, detected: 0, undetected: 0, errors: 0, unsealable: 0, detection_percent: null, crashed: 0, exit_codes: {}, undetected_fields: new Set() });

// Errors (no exit code) and unsealable edits (no canonical form to reseal) are counted apart and
// left out of the detection rate.
function addRun(summary, code, crashed, field, unsealable = false) {
  summary.mutations += 1;
  const key = code === null ? "none" : String(code);
  summary.exit_codes[key] = (summary.exit_codes[key] ?? 0) + 1;
  if (crashed) summary.crashed += 1;
  if (code === null) {
    summary.errors += 1;
  } else if (unsealable) {
    summary.unsealable += 1;
  } else if (code === 0) {
    summary.undetected += 1;
    summary.undetected_fields.add(generalize(field));
  } else {
    summary.detected += 1;
  }
}

function finishMode(summary) {
  const exitCodes = {};
  for (const key of Object.keys(summary.exit_codes).sort(byText)) exitCodes[key] = summary.exit_codes[key];
  return { ...summary, detection_percent: percent(summary.detected, summary.detected + summary.undetected), exit_codes: exitCodes, undetected_fields: [...summary.undetected_fields].sort(byText) };
}

function summarizeMutations(tasks, results, { skipped, digestLeaves, unaccounted, embedded }) {
  const groups = new Map();
  const totals = Object.fromEntries(MODES.map((mode) => [mode, emptyMode()]));
  const controls = { runs: 0, accepted: 0, rejected: [] };
  tasks.forEach((task, index) => {
    const { code, crashed } = results[index];
    const { vector } = task;
    if (task.mode === "control") {
      controls.runs += 1;
      if (code === 0) controls.accepted += 1;
      else controls.rejected.push(`${vector.project}/${vector.path}`);
      return;
    }
    const key = `${vector.project}\0${vector.type}`;
    if (!groups.has(key)) groups.set(key, { project: vector.project, record_type: vector.type, vectors: new Set(), files: new Map(), ...Object.fromEntries(MODES.map((mode) => [mode, emptyMode()])) });
    const group = groups.get(key);
    group.vectors.add(vector.path);
    const field = task.group === null ? task.field : `${task.group}#${task.field}`;
    addRun(group[task.mode], code, crashed, field, task.unsealable);
    addRun(totals[task.mode], code, crashed, `${vector.project}:${vector.type}:${field}`, task.unsealable);
    if (task.group !== null) {
      if (!group.files.has(task.group)) group.files.set(task.group, Object.fromEntries(MODES.map((mode) => [mode, emptyMode()])));
      addRun(group.files.get(task.group)[task.mode], code, crashed, task.field, task.unsealable);
    }
  });
  const byType = [...groups.values()]
    .sort((a, b) => byText(a.project, b.project) || byText(a.record_type, b.record_type))
    .map((group) => {
      const row = { project: group.project, record_type: group.record_type, vectors: group.vectors.size, embedded_digest_leaves_not_mutated: digestLeaves.get(`${group.project}\0${group.record_type}`) ?? 0 };
      for (const mode of MODES) row[mode] = finishMode(group[mode]);
      if (group.files.size > 0) {
        row.files = Object.fromEntries([...group.files.keys()].sort(byText).map((name) => [name, Object.fromEntries(MODES.map((mode) => [mode, finishMode(group.files.get(name)[mode])]))]));
      }
      return row;
    });
  const total = Object.fromEntries(MODES.map((mode) => {
    const { undetected_fields: _fields, ...rest } = finishMode(totals[mode]);
    return [mode, rest];
  }));
  const embeddedRows = Object.entries(embedded).flatMap(([project, rules]) => rules.map(({ document, value, what, derive, covers_file: file }) => ({
    project, document, value, what, resealed: Boolean(derive || file), checked_by_baseline: Boolean(derive || file),
  })));
  return { controls, skipped, embedded_digests: embeddedRows, unaccounted_digest_values: unaccounted, by_type: byType, total };
}

// ---------------------------------------------------------------------------------------------
// Environment and provenance

async function gitSource(root, outDir, projects) {
  const git = (...args) => run("git", ["-C", root, ...args], { maxBuffer: 1 << 20 }).then(({ stdout }) => stdout.trim());
  try {
    const commit = await git("rev-parse", "HEAD");
    const exclude = [":(exclude)scripts/conformance/node_modules"];
    const outRelative = slash(path.relative(root, outDir));
    if (!outRelative.startsWith("..") && !path.isAbsolute(outRelative)) exclude.push(`:(exclude)${outRelative}`);
    const status = await git("status", "--porcelain", "--", "ai-workflows", "scripts/conformance", ...exclude);
    const trees = {};
    // Tree ids survive a squash merge, unlike the commit: equal ids mean byte-identical inputs.
    for (const entry of [...projects.map((project) => `ai-workflows/${project}`), "scripts/conformance/checks", "scripts/conformance/evaluate.mjs"]) {
      trees[entry] = await git("rev-parse", `HEAD:${entry}`).catch(() => null);
    }
    return { commit, dirty: status !== "", tree_ids: trees };
  } catch {
    return { commit: null, dirty: null, tree_ids: {} };
  }
}

const PYTHON_INFO = `
import json, platform, sys
from importlib import metadata
packages = {}
for name in sys.argv[1:]:
    try:
        packages[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        packages[name] = None
print(json.dumps({"python": platform.python_version(), "implementation": platform.python_implementation(), "packages": packages}))
`;

async function pythonInfo(bin, packages, env) {
  try {
    const { stdout } = await run(path.join(bin, "python"), ["-I", "-c", PYTHON_INFO, ...packages], { env });
    return JSON.parse(stdout);
  } catch {
    return { python: null, implementation: null, packages: Object.fromEntries(packages.map((name) => [name, null])) };
  }
}

// Version arguments per tool; the first line of output that names a version is recorded.
const VERSION_ARGS = { opa: ["version"], cedar: ["--version"], cosign: ["version"] };

/** Each external tool on the verifiers' PATH, as its version line, or null when absent. */
async function toolsOnPath(env) {
  const found = {};
  for (const tool of EXTERNAL_TOOLS) {
    found[tool] = null;
    for (const dir of env.PATH.split(path.delimiter)) {
      const file = path.join(dir, tool);
      if (!(await fs.access(file, fsConstants.X_OK).then(() => true, () => false))) continue;
      const output = await run(file, VERSION_ARGS[tool], { env, timeout: 30_000 }).then(({ stdout, stderr }) => `${stdout}\n${stderr}`, () => "");
      found[tool] = output.split("\n").map((line) => line.trim()).find((line) => /\d+\.\d+/.test(line)) ?? "found (version unknown)";
      break;
    }
  }
  return found;
}

export function machine() {
  const cpus = os.cpus();
  return {
    platform: os.platform(),
    release: os.release(),
    os_version: typeof os.version === "function" ? os.version() : null,
    arch: os.arch(),
    cpu: cpus[0]?.model ?? null,
    cpus: cpus.length,
    memory_gib: Math.round(os.totalmem() / 2 ** 30),
  };
}

// ---------------------------------------------------------------------------------------------
// (d) Latency

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const round1 = (value) => Math.round(value * 10) / 10;

async function timed(argv, options) {
  const start = process.hrtime.bigint();
  await runProcess(argv, options);
  return Number(process.hrtime.bigint() - start) / 1e6;
}

async function measureLatency(valid, runs, { bin, env, tmp }) {
  const perType = new Map();
  for (const vector of valid) {
    const argv = commandFor(vector, vector.abs, bin);
    await runProcess(argv, { env, cwd: tmp }); // warm-up, not timed
    const times = [];
    for (let index = 0; index < runs; index += 1) times.push(await timed(argv, { env, cwd: tmp }));
    const key = `${vector.project}\0${vector.type}`;
    if (!perType.has(key)) perType.set(key, { project: vector.project, record_type: vector.type, command: vector.spec.verify.command.filter((arg) => arg !== "{path}").join(" "), medians: [] });
    perType.get(key).medians.push(median(times));
  }
  let startup = null;
  const python = path.join(bin, "python");
  if (await fs.access(python, fsConstants.X_OK).then(() => true, () => false)) {
    await runProcess([python, "-c", "pass"], { env, cwd: tmp });
    const times = [];
    for (let index = 0; index < runs; index += 1) times.push(await timed([python, "-c", "pass"], { env, cwd: tmp }));
    startup = round1(median(times));
  }
  const byType = [...perType.values()]
    .sort((a, b) => byText(a.project, b.project) || byText(a.record_type, b.record_type))
    .map(({ medians, ...row }) => ({ ...row, vectors: medians.length, median_ms: round1(median(medians)), min_ms: round1(Math.min(...medians)), max_ms: round1(Math.max(...medians)) }));
  return { runs_per_vector: runs, statistic: "median of each vector's runs after one untimed warm-up; per type, the median, minimum and maximum of those medians", python_startup_ms: startup, by_type: byType, machine: machine() };
}

// ---------------------------------------------------------------------------------------------
// Evaluation

/**
 * Run the whole evaluation. Options: root, bin, jobs, latencyRuns (0 skips latency), inheritPath,
 * outDir (only to keep it out of the dirty check), log (progress lines).
 */
export async function evaluate({ root, bin, jobs = os.availableParallelism?.() ?? os.cpus().length, latencyRuns = 0, inheritPath = false, outDir = root, log = () => {}, embedded = EMBEDDED_DIGESTS }) {
  const { manifests, vectors } = await loadVectors(root);
  if (vectors.length === 0) throw new UsageError(`no conformance manifests under ${root}`);
  await checkBin(vectors, bin);
  const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "conformance-evaluate-"));
  try {
    const env = verifierEnvironment(bin, { inheritPath, home: tmp });
    const context = { tmp, bin, env };

    // (a) counts
    const byProject = {};
    for (const vector of vectors) {
      byProject[vector.project] ??= { package: vector.package, valid: 0, tampered: 0, invalid: 0, total: 0 };
      byProject[vector.project][vector.expect] += 1;
      byProject[vector.project].total += 1;
    }
    const counts = { by_project: byProject, total: Object.fromEntries([...KINDS, "total"].map((kind) => [kind, Object.values(byProject).reduce((sum, row) => sum + row[kind], 0)])) };

    // (b) baseline and verifier exit codes
    log(`verifiers: ${vectors.length} vectors`);
    const specs = digestSpecs(vectors);
    const schemaCache = new Map();
    const schemasFor = (vector) => {
      if (!schemaCache.has(vector.projectDir)) schemaCache.set(vector.projectDir, loadProjectSchemas(vector.projectDir));
      return schemaCache.get(vector.projectDir);
    };
    const exits = await pool(vectors, jobs, (vector) => runVerifier(commandFor(vector, vector.abs, bin), { env, cwd: tmp }));
    const perVector = [];
    for (const [index, vector] of vectors.entries()) {
      const row = { project: vector.project, path: vector.path, expect: vector.expect, record_type: vector.type, manifest_exit_code: vector.spec.verify.exit_code, verifier_exit_code: exits[index].code };
      for (const mode of BASELINES) {
        const reasons = await baselineReasons(vector, mode, { specs, schemasFor, embedded });
        row[`baseline_${mode}`] = reasons.length === 0 ? "accept" : "reject";
        if (reasons.length > 0) row[`baseline_${mode}_reasons`] = reasons;
      }
      perVector.push(row);
    }
    const baselineSummary = (rows) => ({
      vectors: rows.length,
      baseline_strict_accepts: rows.filter((row) => row.baseline_strict === "accept").length,
      baseline_json_parse_accepts: rows.filter((row) => row.baseline_json_parse === "accept").length,
      verifier_rejects: rows.filter((row) => row.verifier_exit_code !== null && row.verifier_exit_code !== 0).length,
      verifier_exit_code_as_manifest: rows.filter((row) => row.verifier_exit_code === row.manifest_exit_code).length,
    });
    const baseline = { by_project: {}, total: {}, vectors: perVector };
    for (const project of Object.keys(byProject)) {
      baseline.by_project[project] = Object.fromEntries(KINDS.map((kind) => [kind, baselineSummary(perVector.filter((row) => row.project === project && row.expect === kind))]));
    }
    baseline.total = Object.fromEntries(KINDS.map((kind) => [kind, baselineSummary(perVector.filter((row) => row.expect === kind))]));

    // (c) mutations
    const valid = vectors.filter((vector) => vector.expect === "valid");
    const skipped = [];
    const { tasks, digestLeaves } = await mutationTasks(valid, skipped, { forms: canonicalForms(vectors), embedded });
    const unaccounted = await unaccountedDigests(valid, embedded);
    log(`mutations: ${tasks.length} verifier runs (${valid.length} controls), ${jobs} at a time`);
    let done = 0;
    const results = await pool(tasks, jobs, async (task, index) => {
      const result = await runTask(task, index, context);
      done += 1;
      if (done % 1000 === 0) log(`  ${done}/${tasks.length}`);
      return result;
    });
    const mutations = summarizeMutations(tasks, results, { skipped, digestLeaves, unaccounted, embedded });

    // (d) sizes and latency
    const sizeRows = new Map();
    for (const vector of valid) {
      const key = `${vector.project}\0${vector.type}`;
      if (!sizeRows.has(key)) sizeRows.set(key, { project: vector.project, record_type: vector.type, sizes: [] });
      sizeRows.get(key).sizes.push(await sizeOf(vector.abs));
    }
    const sizes = {
      unit: "bytes; a directory vector counts every file in it",
      by_type: [...sizeRows.values()]
        .sort((a, b) => byText(a.project, b.project) || byText(a.record_type, b.record_type))
        .map(({ sizes: list, ...row }) => ({ ...row, vectors: list.length, min: Math.min(...list), median: median(list), max: Math.max(...list) })),
    };
    let latency = null;
    if (latencyRuns > 0) {
      log(`latency: ${latencyRuns} runs per valid vector`);
      latency = await measureLatency(valid, latencyRuns, context);
    }

    const packages = [...new Set(manifests.map((manifest) => manifest.package))];
    const result = {
      format: 1,
      generated_by: "scripts/conformance/evaluate.mjs",
      source: await gitSource(root, outDir, manifests.map((manifest) => manifest.project)),
      manifests,
      environment: {
        ...(await pythonInfo(bin, packages, env)),
        node: process.version,
        verifier_path: inheritPath ? "--bin, then the caller's PATH" : "--bin, /usr/bin, /bin",
        external_tools_on_path: await toolsOnPath(env),
      },
      counts,
      baseline,
      mutations,
      sizes,
    };
    if (latency !== null) result.latency = latency;
    return result;
  } finally {
    await fs.rm(tmp, { recursive: true, force: true });
  }
}

/** Problems that make the run untrustworthy: a verifier disagreeing with its manifest, a control rejected, or runs without an exit code. */
export function problems(result) {
  const found = [];
  for (const row of result.baseline.vectors) {
    if (row.verifier_exit_code !== row.manifest_exit_code) found.push(`${row.project}/${row.path}: verifier exited ${row.verifier_exit_code}, manifest says ${row.manifest_exit_code}`);
  }
  for (const vector of result.mutations.controls.rejected) found.push(`${vector}: the re-serialized, unmutated vector was rejected, so its mutations are confounded`);
  for (const mode of MODES) {
    const { errors } = result.mutations.total[mode];
    if (errors > 0) found.push(`${errors} ${mode} mutation runs ended without an exit code after ${ATTEMPTS} attempts; they are left out of the rates`);
  }
  for (const value of result.mutations.unaccounted_digest_values) {
    found.push(`${value}: a 64-hex value that is neither a manifest digest nor in EMBEDDED_DIGESTS, so resealing may leave it stale`);
  }
  if (result.caller_path) found.push(...result.caller_path.problems.map((problem) => `with the caller's PATH: ${problem}`));
  return found;
}

/**
 * The same sweep with the caller's PATH, where OPA or Cedar may re-evaluate frozen decisions:
 * its tools, totals, and every record type whose counts differ from the default run.
 */
export function callerPathComparison(base, other) {
  const differences = [];
  for (const row of base.mutations.by_type) {
    const twin = other.mutations.by_type.find((item) => item.project === row.project && item.record_type === row.record_type);
    for (const mode of MODES) {
      if (!twin || twin[mode].detected !== row[mode].detected || twin[mode].undetected !== row[mode].undetected) {
        differences.push({
          project: row.project, record_type: row.record_type, mode,
          detected: twin?.[mode].detected ?? null,
          undetected_only_with_default_path: row[mode].undetected_fields.filter((field) => !(twin?.[mode].undetected_fields ?? []).includes(field)),
          undetected_only_with_caller_path: (twin?.[mode].undetected_fields ?? []).filter((field) => !row[mode].undetected_fields.includes(field)),
        });
      }
    }
  }
  return {
    verifier_path: other.environment.verifier_path,
    external_tools_on_path: other.environment.external_tools_on_path,
    total: other.mutations.total,
    baseline_total: other.baseline.total,
    differences,
    problems: problems(other),
  };
}

// ---------------------------------------------------------------------------------------------
// RESULTS.md

const number = (value) => value.toLocaleString("en-US");
const rate = (summary) => `${number(summary.detected)}/${number(summary.detected + summary.undetected)} (${summary.detection_percent?.toFixed(1) ?? "-"}%)`;
const toolList = (tools) => Object.entries(tools).filter(([, version]) => version).map(([tool, version]) => `${tool} (${version})`);
const fields = (list) => (list.length === 0 ? "none" : list.map((field) => `\`${field}\``).join(", "));

export function renderMarkdown(result) {
  const lines = [];
  const add = (...items) => lines.push(...items);
  const { source, environment: env, counts, baseline, mutations, sizes, latency } = result;
  const packages = Object.entries(env.packages).map(([name, version]) => `${name} ${version ?? "(not installed)"}`).join(", ");
  const tools = toolList(env.external_tools_on_path);

  add("# Offline evaluation results", "");
  add(`Generated by \`${result.generated_by}\` (\`npm run evaluate\`). Every number below is in \`results.json\` next to this file.`, "");
  add(`- Source: commit \`${source.commit ?? "unknown"}\`${source.dirty ? ", with uncommitted changes under ai-workflows/ or scripts/conformance/" : source.dirty === false ? ", clean working tree" : ""}.`);
  add(`- Verifiers: each manifest's \`verify.command\`, run as a subprocess. Python ${env.python ?? "unknown"} (${env.implementation ?? "?"}); ${packages}. Node ${env.node}.`);
  add(`- Verifier PATH: ${env.verifier_path}. External tools found on it: ${tools.length === 0 ? "none, so OPA and Cedar decisions in decision-control records are checked digest-only, not re-evaluated" : tools.join(", ")}.`, "");
  add("| Manifest | Vectors | SHA-256 |", "| --- | --- | --- |");
  for (const manifest of result.manifests) add(`| \`${manifest.path}\` | ${manifest.vectors} | \`${manifest.sha256}\` |`);

  add("", "## (a) Conformance vectors", "", "| Project | Package | Valid | Tampered | Invalid | Total |", "| --- | --- | --- | --- | --- | --- |");
  for (const [project, row] of Object.entries(counts.by_project)) add(`| ${project} | \`${row.package}\` | ${row.valid} | ${row.tampered} | ${row.invalid} | ${row.total} |`);
  add(`| **All** | | ${counts.total.valid} | ${counts.total.tampered} | ${counts.total.invalid} | ${counts.total.total} |`);

  add("", "## (b) Hash + JSON Schema baseline against the verifiers", "");
  add("The baseline accepts a vector when every document it declares validates against its committed JSON Schema (Ajv 2020-12, set up as in `verify.mjs`) and every digest it can recompute from the vector alone matches. Those are the digests the valid vectors of the same schema declare in the manifests (RFC 8785, python-json-v1 or file bytes), plus the embedded digests listed under (c) as checked by the baseline. It does not check digests that name files outside the vector, and it replays nothing. *Strict* reads JSON as `verify.mjs` does, rejecting duplicate keys. *JSON.parse* keeps the last of duplicate keys. Both reject NaN and Infinity; Python's `json.loads` accepts them by default. *Verifier rejects* counts exit codes other than 0; a run without an exit code counts as neither.", "");
  add("| Project | Kind | Vectors | Baseline accepts (strict) | Baseline accepts (JSON.parse) | Verifier rejects | Verifier exit code as in manifest |", "| --- | --- | --- | --- | --- | --- | --- |");
  const baselineRow = (label, kind, row) => add(`| ${label} | ${kind} | ${row.vectors} | ${row.baseline_strict_accepts} | ${row.baseline_json_parse_accepts} | ${row.verifier_rejects} | ${row.verifier_exit_code_as_manifest} |`);
  for (const [project, kinds] of Object.entries(baseline.by_project)) for (const kind of KINDS) baselineRow(project, kind, kinds[kind]);
  for (const kind of KINDS) baselineRow("**All**", kind, baseline.total[kind]);
  for (const kind of ["tampered", "invalid"]) {
    const accepted = baseline.vectors.filter((row) => row.expect === kind && row.baseline_strict === "accept");
    add("", `${kind[0].toUpperCase()}${kind.slice(1)} vectors the strict baseline accepts (${accepted.length}): ${accepted.length === 0 ? "none" : accepted.map((row) => `\`${row.project}/${row.path}\``).join(", ")}.`);
  }

  add("", "## (c) Single-leaf mutations", "");
  add("Every JSON leaf of every valid vector is changed once: integer +1, float +0.125 (x2 when |x| >= 1e6), string + `x`, boolean flipped, null to `x`. The edited record goes through its verifier; *detected* means an exit code other than 0.", "");
  add("- **Stale** leaves every digest as it was.");
  add("- **Resealed** recomputes every digest the verifier checks, as someone who edits a record and re-hashes it would. The embedded digests below come first, then the manifest's digests, innermost first. Each digest uses the canonical form the edited record's `schema_version` requires; which version uses which form is learned from the valid vectors, so an edit from decision-control record schema 3 to 4 is resealed in RFC 8785. In a directory vector, the SHA-256s in `provenance.json` come last.");
  add("- Resealing rewrites digests, not copies. An OPA input or a Cedar request repeats parts of the proposal, so an edit to a repeated field is caught by that comparison.");
  add("- Digest fields, declared or embedded, are not mutated. In directory vectors only JSON files in compact sorted form are mutated; JSONL files and `provenance.json` are not.", "");
  add("Digests the verifiers check that the manifests do not declare:", "", "| Project | Document | Digest | Of | Resealed and checked by the baseline |", "| --- | --- | --- | --- | --- |");
  for (const rule of mutations.embedded_digests) add(`| ${rule.project} | \`${rule.document}\` | \`${rule.value}\` | ${rule.what} | ${rule.resealed ? "yes" : "no: no edit here changes those files, and only replay knows which run they belong to"} |`);
  const notMutated = mutations.by_type.reduce((sum, row) => sum + row.embedded_digest_leaves_not_mutated, 0);
  add("", `${notMutated} embedded digest leaves in the valid vectors are left unmutated. ${mutations.unaccounted_digest_values.length === 0 ? "A scan of the valid vectors finds no other 64-hex value." : `Unaccounted 64-hex values: ${mutations.unaccounted_digest_values.map((value) => `\`${value}\``).join(", ")}.`}`, "");
  add("| Project | Record type | Vectors | Mutations per mode | Stale detected | Resealed detected |", "| --- | --- | --- | --- | --- | --- |");
  for (const row of mutations.by_type) {
    add(`| ${row.project} | ${row.record_type} | ${row.vectors} | ${number(row.stale.mutations)} | ${rate(row.stale)} | ${rate(row.resealed)} |`);
    for (const [name, file] of Object.entries(row.files ?? {})) add(`| | ${row.record_type}: ${name} | | ${number(file.stale.mutations)} | ${rate(file.stale)} | ${rate(file.resealed)} |`);
  }
  add(`| **All** | | ${counts.total.valid} | ${number(mutations.total.stale.mutations)} | **${rate(mutations.total.stale)}** | **${rate(mutations.total.resealed)}** |`, "");
  const caller = result.caller_path;
  if (caller) {
    const callerTools = toolList(caller.external_tools_on_path);
    add(`With the caller's PATH (${callerTools.length === 0 ? "no external tools found" : callerTools.join(", ")}), the same sweep detects stale ${rate(caller.total.stale)} and resealed ${rate(caller.total.resealed)}.${caller.differences.length === 0 ? " No record type differs." : ` It differs in ${caller.differences.map((row) => `${row.project} ${row.record_type} ${row.mode} (${number(row.detected)} detected${row.undetected_only_with_default_path.length ? `; caught only with the caller's PATH: ${fields(row.undetected_only_with_default_path)}` : ""}${row.undetected_only_with_caller_path.length ? `; missed only with it: ${fields(row.undetected_only_with_caller_path)}` : ""})`).join("; ")}.`}`, "");
  }
  const unsealable = mutations.total.resealed.unsealable;
  add(unsealable === 0 ? "Every resealed edit could be resealed." : `${unsealable} resealed edits have no canonical form to reseal, because they leave RFC 8785's range. Their digests stay stale, and the rates leave them out.`);
  const crashed = MODES.map((mode) => mutations.total[mode].crashed).reduce((a, b) => a + b, 0);
  const errors = MODES.map((mode) => mutations.total[mode].errors).reduce((a, b) => a + b, 0);
  add(`Controls: ${mutations.controls.accepted} of ${mutations.controls.runs} valid vectors still verify after being rewritten unmutated, so the rewrite itself is not what the verifiers detect.${mutations.controls.rejected.length ? ` Rejected: ${mutations.controls.rejected.join(", ")}.` : ""} ${crashed === 0 ? "No run ended in an uncaught Python exception." : `${crashed} runs ended in an uncaught Python exception; they count as detected.`} ${errors === 0 ? "Every run returned an exit code (a run killed before it exits is retried up to three times)." : `${errors} runs never returned an exit code; the rates leave them out.`}`);
  if (mutations.skipped.length > 0) add(`Skipped files: ${mutations.skipped.map((item) => `\`${item.vector}/${item.file}\``).join(", ")} (${[...new Set(mutations.skipped.map((item) => item.reason))].join("; ")}).`);
  for (const mode of MODES) {
    add("", `### Fields whose edits go undetected, ${mode}`, "");
    const missed = mutations.by_type.filter((row) => row[mode].undetected > 0);
    if (missed.length === 0) add("None.");
    for (const row of missed) add(`- ${row.project} ${row.record_type} (${row[mode].undetected}): ${fields(row[mode].undetected_fields)}`);
  }

  add("", "### What the mutation rates show, and what they do not", "");
  add("- Digests detect change, not forgery: whoever edits a record can recompute its hashes ([DECISION_RECORDS.md](../../../docs/DECISION_RECORDS.md#compatibility-and-limits)). A resealed edit is caught when replay recomputes something from the edited field, or finds that it no longer matches a copy elsewhere in the record.");
  add("- Fields no recomputation depends on stay bound only by a signature (`--require-signature`): free text such as review and event notes or question instructions, caller-supplied labels such as `recommendation.model`, `question_version`, `proposed_by` and `produced_by.version`, inputs whose edit leaves the recomputed verdict unchanged, and `schema_version` where the next version reads the same record and the edit is resealed in that version's canonical form. The lists above name them for this corpus.");
  add("- One edit per value type, one leaf at a time, on vectors written by the same authors as the verifiers. The rates describe this corpus and operator, not records in general or an adversary who edits several fields together.");

  add("", "## Record sizes", "", `Valid vectors, ${sizes.unit}.`, "", "| Project | Record type | Vectors | Min | Median | Max |", "| --- | --- | --- | --- | --- | --- |");
  for (const row of sizes.by_type) add(`| ${row.project} | ${row.record_type} | ${row.vectors} | ${number(row.min)} | ${number(row.median)} | ${number(row.max)} |`);

  add("", "## (d) CLI verify latency", "");
  if (!latency) {
    add("Not measured in this run (`--latency-runs 0`): wall time depends on the machine, so it is kept out of the committed, deterministic results.");
  } else {
    const m = latency.machine;
    add(`Wall time of one verifier process per valid vector, ${latency.runs_per_vector} runs each (${latency.statistic}). Machine: ${m.cpu ?? "unknown CPU"}, ${m.cpus} CPUs, ${m.memory_gib} GiB; ${m.platform} ${m.release} (${m.os_version ?? ""}), ${m.arch}. Python ${env.python}, Node ${env.node}.${latency.python_startup_ms === null ? "" : ` A bare \`python -c pass\` takes ${latency.python_startup_ms} ms on the same machine.`}`, "");
    add("| Project | Record type | Command | Vectors | Median ms | Min ms | Max ms |", "| --- | --- | --- | --- | --- | --- | --- |");
    for (const row of latency.by_type) add(`| ${row.project} | ${row.record_type} | \`${row.command}\` | ${row.vectors} | ${row.median_ms} | ${row.min_ms} | ${row.max_ms} |`);
  }
  return `${lines.join("\n")}\n`;
}
