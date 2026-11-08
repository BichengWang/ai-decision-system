# Conformance cross-check

A Node program, with no Python in the loop, that re-checks every conformance
manifest under `ai-workflows/<project>/conformance/manifest.json`:

1. the manifest matches [`manifest.schema.json`](manifest.schema.json);
2. every `documents` entry validates (or fails, as declared by `schema_valid`)
   against its JSON Schema with Ajv 2020-12 (strict mode, `ajv-formats`);
3. for every `valid` vector, every `digests` entry is recomputed from the vector
   and compared with the recorded digest, using a JavaScript canonicalizer that
   shares no code with the Python packages.

It exists so that a second implementation, in another language, disagrees loudly
if a Python canonicalizer, a schema, or a vector drifts. It checks internal
consistency of committed vectors. It does not run the Python verifiers (each
project's own tests do that), authenticate anything, or show adoption.

```sh
cd scripts/conformance
npm ci                      # pinned: package.json + package-lock.json
node --test                 # self-tests: a wrong digest, a schema violation and a
                            # non-canonical file are each caught
node verify.mjs             # all manifests in this checkout (exit 1 on any discrepancy)
node verify.mjs /path/to/checkout
```

With no manifests, `verify.mjs` prints `0 manifests found` and exits 0. CI runs
this as the `conformance (node)` check of
[`.github/workflows/conformance.yml`](../../.github/workflows/conformance.yml) on
every change to a manifest, vector, package `schema/` directory or this folder.

## Offline evaluation

`evaluate.mjs` runs every vector through its package verifier, the manifest's
`verify.command` as a subprocess, and writes `results.json` and `RESULTS.md`:
vector counts, a hash + JSON Schema baseline against the verifiers, a stale and a
resealed single-leaf mutation matrix per record type, record sizes and CLI verify
latency. It needs the three packages installed from this checkout:

```sh
python3 -m venv /tmp/ads-venv
/tmp/ads-venv/bin/pip install ../../ai-workflows/{experiment-gate,jev-decision,decision-control}
npm run evaluate -- --bin /tmp/ads-venv/bin --out /tmp/ads-eval   # ~8,700 runs, minutes
```

Verifiers get a PATH of `--bin`, `/usr/bin` and `/bin` only, so OPA and Cedar
decisions replay digest-only; `--inherit-path` passes the caller's PATH instead.
`--latency-runs 0` skips latency. [`results/`](results/RESULTS.md) holds one run
without latency, which is deterministic; regenerate it with `--out results
--latency-runs 0` when vectors or verifiers change. It names the manifests'
SHA-256s, the source commit and the git tree ids of the packages and the
evaluator, which stay the same after a squash merge. `node --test` covers the
evaluator with a stub verifier, so CI needs no Python; CI does not run the sweep.

## Manifest rules

The format is specified in [DECISION_RECORDS](../../docs/DECISION_RECORDS.md#conformance-vectors).
Beyond the JSON Schema, the checker enforces:

- `path` and `canonical_file` are relative to `conformance/`. `documents[].path`,
  `digests[].document` and `covers_file` are relative to the vector path: `.` for
  a file vector, a file inside it for a directory vector. `schema` is relative to
  `ai-workflows/<project>/`. Nothing may leave its base directory.
- A vector lives under the directory named by its `expect` (`valid/`, `tampered/`,
  `invalid/`) and `verify.exit_code` is 0, 1 or 2 accordingly.
- Every file under `valid/`, `tampered/` and `invalid/` is referenced by a vector,
  digest `canonical_file` or `covers_file`, so no vector goes unchecked.
- A `valid` vector declares a non-empty `documents` list, and every digest's
  `document` has a `documents` entry, so the record it digests is schema-validated.
- Every schema file under `ai-workflows/<project>/*/schema/`, referenced or not,
  has a string `$id`, loads into one Ajv instance (so `$ref` between files
  resolves) and compiles in strict mode.
- Digests of `tampered` and `invalid` vectors are not recomputed; they are
  expected to disagree with their content.

## Digest recomputation

Documents are read with a strict JSON reader (`checks/json.mjs`): duplicate object
keys are an error, and an integer literal outside +-(2^53-1) is kept exactly as a
BigInt instead of being rounded.

| `canonicalization` | Check |
| --- | --- |
| `rfc8785` | Re-canonicalize the covered value (after removing `exclude` members; each must exist) per RFC 8785 and compare byte for byte with `canonical_file`; SHA-256 of those bytes must equal the recorded digest. Integers outside the I-JSON range, non-finite numbers and lone surrogates fail. |
| `python-json-v1` | The covered value is read from the document keeping each number's literal (so `0` and `0.0`, and `0.0` and `-0.0`, stay different), then serialized Python's way: keys sorted by code point, compact separators, unescaped non-ASCII, integers as canonical decimal, floats as Python's `repr` of the parsed double (shortest round-trip digits, fixed notation for exponents -4 to 15, otherwise `1e-07` / `1.5e+16`). The bytes must equal `canonical_file`, and their SHA-256 must equal the recorded digest. The float spelling is cross-checked against Python on 6000 doubles in the self-tests. |
| `bytes` | SHA-256 of the exact bytes of `covers_file` must equal the recorded digest. |

Schema validation reads documents with `JSON.parse`, like any JSON Schema
consumer, so a duplicate key is not a schema violation; duplicate keys are caught
by the digest reader and by each package's own verifier.

## Dependencies

`ajv` and `ajv-formats` are the only dependencies, pinned to exact versions in
`package.json` and `package-lock.json`; CI installs with `npm ci`. The checker
uses the Ajv library rather than `ajv-cli` so that one process can resolve
`$ref` between the schema files of a project and report failures per vector.
Update both pins together, run `node --test`, and commit the lockfile.
`test/jcs_vectors.json` is the shared RFC 8785 vector file also committed in each
package's tests.
