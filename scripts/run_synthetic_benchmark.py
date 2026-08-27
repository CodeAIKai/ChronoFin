#!/usr/bin/env python3
"""Run the fully offline multi-cluster synthetic evaluator benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.evaluator.benchmark import benchmark_json, run_synthetic_benchmark


def main() -> None:
    result = run_synthetic_benchmark()
    output = ROOT / "results" / "synthetic_benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(benchmark_json(result), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "base_tasks": result["coverage"]["base_tasks"],
        "total_mutation_runs": result["coverage"]["total_mutation_runs"],
        "PDA": result["metrics"]["paired_discrimination_accuracy"],
        "IVR": result["metrics"]["invariance_violation_rate"],
        "severity_drop_spearman": result["metrics"]["severity_drop_spearman"],
        "bootstrap_95_ci": result["cluster_bootstrap_95_ci"]["primary_metric_ci"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
