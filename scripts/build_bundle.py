"""Copy the benchmark into costlab/_bundle so it ships inside the wheel.

Run before building a release (the bundle is generated, never committed):

    python scripts/build_bundle.py
    python -m pip wheel --no-deps . -w dist

What ships: prices.yaml, each workload's tasks.jsonl, every recorded answer in cache/, and
results/runs.json. That is exactly what `costlab rebuild` needs to reproduce the published
numbers on a fresh install with no API key.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUNDLE = REPO / "costlab" / "_bundle"


def build(repo: Path = REPO, bundle: Path = BUNDLE) -> dict[str, int]:
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    counts = {"prices": 0, "workloads": 0, "cache": 0, "manifest": 0}

    shutil.copy2(repo / "prices.yaml", bundle / "prices.yaml")
    counts["prices"] = 1
    for tasks in sorted((repo / "workloads").glob("*/tasks.jsonl")):
        target = bundle / "workloads" / tasks.parent.name / "tasks.jsonl"
        target.parent.mkdir(parents=True)
        shutil.copy2(tasks, target)
        counts["workloads"] += 1
    for entry in sorted((repo / "cache").glob("*/*.json")):
        target = bundle / "cache" / entry.parent.name / entry.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)
        counts["cache"] += 1
    manifest = repo / "results" / "runs.json"
    if manifest.exists():
        (bundle / "results").mkdir()
        shutil.copy2(manifest, bundle / "results" / "runs.json")
        counts["manifest"] = 1
    return counts


if __name__ == "__main__":
    counts = build()
    print(f"bundled into {BUNDLE}: {counts}")
    if not all(counts.values()):
        sys.exit("bundle incomplete: every part above must be at least 1")
