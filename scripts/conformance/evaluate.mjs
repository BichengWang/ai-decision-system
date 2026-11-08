#!/usr/bin/env node
// Usage: node evaluate.mjs --bin VENV/bin --out DIR [--root CHECKOUT] [--jobs N] [--latency-runs N]
//                          [--inherit-path | --compare-inherit-path]
// Runs every conformance vector, and single-leaf mutations of every valid one, through the package
// verifiers named by the manifests (console scripts in --bin), and writes DIR/results.json and
// DIR/RESULTS.md. Exits 1 when a verifier disagrees with its manifest or a control run fails,
// 2 on usage or unexpected errors. See README.md, "Offline evaluation".

import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { callerPathComparison, evaluate, problems, renderMarkdown, UsageError } from "./checks/evaluate.mjs";

const USAGE = "usage: node evaluate.mjs --bin VENV/bin --out DIR [--root CHECKOUT] [--jobs N] [--latency-runs N (default 10, 0 skips)] [--inherit-path | --compare-inherit-path]";
const here = path.dirname(fileURLToPath(import.meta.url));

function count(text, name, minimum) {
  if (!/^[0-9]+$/.test(text) || Number(text) < minimum) throw new UsageError(`--${name} must be an integer >= ${minimum}`);
  return Number(text);
}

try {
  const { values } = parseArgs({
    options: {
      bin: { type: "string" },
      out: { type: "string" },
      root: { type: "string" },
      jobs: { type: "string" },
      "latency-runs": { type: "string" },
      "inherit-path": { type: "boolean", default: false },
      "compare-inherit-path": { type: "boolean", default: false },
      help: { type: "boolean", short: "h", default: false },
    },
  });
  if (values.help) {
    console.log(USAGE);
    process.exit(0);
  }
  if (!values.bin || !values.out) throw new UsageError("--bin and --out are required");
  if (values["inherit-path"] && values["compare-inherit-path"]) throw new UsageError("--compare-inherit-path compares against the default PATH; drop --inherit-path");
  const outDir = path.resolve(values.out);
  const started = Date.now();
  const options = {
    root: path.resolve(values.root ?? path.join(here, "..", "..")),
    bin: path.resolve(values.bin),
    jobs: values.jobs === undefined ? (os.availableParallelism?.() ?? os.cpus().length) : count(values.jobs, "jobs", 1),
    inheritPath: values["inherit-path"],
    outDir,
    log: (line) => console.error(line),
  };
  const result = await evaluate({ ...options, latencyRuns: values["latency-runs"] === undefined ? 10 : count(values["latency-runs"], "latency-runs", 0) });
  if (values["compare-inherit-path"]) {
    console.error("again with the caller's PATH:");
    result.caller_path = callerPathComparison(result, await evaluate({ ...options, inheritPath: true, latencyRuns: 0 }));
  }
  await fs.mkdir(outDir, { recursive: true });
  await fs.writeFile(path.join(outDir, "results.json"), `${JSON.stringify(result, null, 2)}\n`);
  await fs.writeFile(path.join(outDir, "RESULTS.md"), renderMarkdown(result));

  const { total } = result.baseline;
  const { stale, resealed } = result.mutations.total;
  console.log(`vectors: ${result.counts.total.total} (${result.counts.total.valid} valid, ${result.counts.total.tampered} tampered, ${result.counts.total.invalid} invalid)`);
  console.log(`baseline (strict) accepts ${total.tampered.baseline_strict_accepts}/${total.tampered.vectors} tampered and ${total.invalid.baseline_strict_accepts}/${total.invalid.vectors} invalid; verifiers reject ${total.tampered.verifier_rejects}/${total.tampered.vectors} and ${total.invalid.verifier_rejects}/${total.invalid.vectors}`);
  console.log(`mutations: stale ${stale.detected}/${stale.mutations} detected (${stale.detection_percent}%), resealed ${resealed.detected}/${resealed.mutations} (${resealed.detection_percent}%)`);
  console.log(`wrote ${path.join(outDir, "results.json")} and RESULTS.md in ${((Date.now() - started) / 1000).toFixed(1)} s`);
  const found = problems(result);
  if (found.length > 0) {
    console.error(`\nevaluate: ${found.length} problems:`);
    for (const problem of found) console.error(`  - ${problem}`);
    process.exit(1);
  }
} catch (error) {
  if (error instanceof UsageError || error?.code?.startsWith?.("ERR_PARSE_ARGS")) {
    console.error(`evaluate: ${error.message}\n${USAGE}`);
  } else {
    console.error(`evaluate: unexpected error: ${error.stack ?? error}`);
  }
  process.exit(2);
}
