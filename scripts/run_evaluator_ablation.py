#!/usr/bin/env python3
"""Run the fully offline evaluator-component ablation study."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.evaluator.ablation import ablation_json, run_evaluator_ablation


def main() -> None:
    result = run_evaluator_ablation()
    output = ROOT / "results" / "evaluator_ablation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(ablation_json(result), encoding="utf-8")
    compact = {
        name: {
            "destructive_detection_rate": values["destructive_detection_rate"],
            "invariance_violation_rate": values["invariance_violation_rate"],
        }
        for name, values in result["strategy_results"].items()
    }
    print(json.dumps({
        "output": str(output),
        "coverage": result["coverage"],
        "strategy_results": compact,
        "paired_component_gains": result["paired_component_gains"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

