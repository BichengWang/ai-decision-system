"""Record installed distribution identities and numerical-library configuration."""
import hashlib
import contextlib
import importlib.metadata
import io
import json
import os
import platform
import subprocess
from pathlib import Path

import numpy
import scipy
import sklearn
from threadpoolctl import threadpool_info


def main():
    root = Path(__file__).resolve().parents[1]
    installed = {}
    for name in ("numpy", "scipy", "scikit-learn", "pytest", "joblib", "threadpoolctl"):
        distribution = importlib.metadata.distribution(name)
        installed[name] = {"version": distribution.version}
        for filename in ("WHEEL", "RECORD", "direct_url.json"):
            content = distribution.read_text(filename)
            if content is not None:
                installed[name][filename + "_sha256"] = hashlib.sha256(content.encode()).hexdigest()
                if filename == "WHEEL":
                    installed[name]["wheel_metadata"] = content.splitlines()
    numerical_config = io.StringIO()
    with contextlib.redirect_stdout(numerical_config):
        numpy.show_config()
        scipy.show_config()
    record = {
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "platform": platform.platform(), "architecture": platform.machine(),
        "processor": platform.processor(),
        "uv_version": subprocess.check_output(["uv", "--version"], text=True).strip(),
        "lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "installed_distributions": installed,
        "numerical_libraries": threadpool_info(),
        "numerical_build_configuration": numerical_config.getvalue(),
        "thread_environment": {key: os.environ.get(key) for key in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")},
        "note": "Installed metadata fingerprints; not an attestation of machine ownership, clean setup, cache use, or downloaded wheel bytes.",
    }
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
