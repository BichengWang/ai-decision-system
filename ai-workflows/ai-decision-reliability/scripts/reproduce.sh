#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 1 || "$1" != /* ]]; then
    echo "Usage: bash scripts/reproduce.sh /absolute/new/output-directory" >&2
    exit 2
fi
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
output=$1
# mkdir, without -p, deliberately refuses existing output and preserves old runs.
mkdir -- "$output"
cd -- "$project_root"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
record_step() {
    local label=$1
    shift
    local started=$SECONDS status=0
    "$@" 2>&1 | tee "$output/$label.log" || status=$?
    printf 'elapsed_seconds=%s exit_status=%s\n' "$((SECONDS - started))" "$status" \
        | tee -a "$output/$label.log"
    return "$status"
}
uv --version | tee "$output/uv-version.txt"
record_step setup uv sync --frozen
uv pip freeze | tee "$output/installed-versions.txt"
uv run --frozen python scripts/environment.py > "$output/environment.json" 2> "$output/environment.log"
record_step tests uv run --frozen python -m pytest -q --basetemp "$output/test-artifacts"
record_step run-a uv run --frozen python -m relia.run --out "$output/repro-a"
record_step run-b uv run --frozen python -m relia.run --out "$output/repro-b"
cmp "$output/repro-a/results.json" "$output/repro-b/results.json"
cmp "$output/repro-a/MANIFEST.json" "$output/repro-b/MANIFEST.json"
uv run --frozen python - "$output" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
hashes = {}
for run in ("repro-a", "repro-b"):
    for name in ("results.json", "MANIFEST.json"):
        path = root / run / name
        hashes[f"{run}/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
with (root / "SHA256.json").open("x") as output:
    json.dump(hashes, output, indent=2)
    output.write("\n")
print("Two-run deterministic artifacts match. Stored-reference comparison and reviewer attestations are separate.")
PY
