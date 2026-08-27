#!/usr/bin/env python3
"""Reproduce the offline submission from a sanitized temporary checkout."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.reproducibility import (
    IGNORED_NAMES,
    canonicalize_temporary_paths,
    tree_fingerprint,
)


OUTPUT = ROOT / "results" / "cleanroom_verification.json"


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name in IGNORED_NAMES or name.endswith((".pyc", ".pyo", ".egg-info"))
    }


def _run(label: str, command: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return {
        "label": label,
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def _build_report(
    *,
    source_fingerprint: str,
    checkout: Path,
    temporary_root: Path,
    cached_pdfs: list[str],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    reproduced_fingerprint = tree_fingerprint(checkout)
    report = {
        "schema_version": "chronofin-cleanroom-v2",
        "source_tree_sha256": source_fingerprint,
        "reproduced_tree_sha256": reproduced_fingerprint,
        "tree_fingerprint_matches": source_fingerprint == reproduced_fingerprint,
        "temporary_checkout_deleted_after_run": True,
        "network_access": False,
        "api_key_environment_removed": True,
        "fresh_virtual_environment": True,
        "inherits_host_build_tooling": True,
        "cached_pdfs_in_checkout": cached_pdfs,
        "commands": results,
        "all_passed": (
            bool(results)
            and all(item["exit_code"] == 0 for item in results)
            and not cached_pdfs
            and source_fingerprint == reproduced_fingerprint
        ),
        "limitations": [
            "This proves reproducibility on the current host Python/toolchain, not on an independent third-party machine.",
            "The fresh venv inherits host site packages because this offline host's ensurepip image omits setuptools; pip remains no-index and installs no dependencies.",
            "The run removes API/proxy variables and expects no network calls, but it does not enforce operating-system-level network isolation.",
            "The temporary Git index validates ignore/tracking rules but is not a public repository or release tag.",
            "No Hy3 network call is made; live traces are checked-in sanitized experiment artifacts.",
            "A prerequisite-mode verifier checks every submission gate except the cleanroom report that it is still constructing; a separate normal verifier must validate the final proof, avoiding circular self-attestation.",
        ],
    }
    # Random temporary paths are irrelevant to the evidence and would make
    # otherwise identical reports differ on every run.
    serialized = json.dumps(report, ensure_ascii=False).replace(
        str(temporary_root),
        "<CLEANROOM>",
    )
    # The report is a public reproducibility artifact.  Host interpreter and
    # site-package locations are irrelevant to the evidence and unnecessarily
    # disclose the runner's filesystem layout, so replace them with stable
    # semantic placeholders.  Apply longer paths first to preserve meaning.
    host_paths: list[tuple[str, str]] = [
        (str(Path(sys.executable).resolve()), "<HOST_PYTHON>"),
        *(
            (str(Path(path).resolve()), "<HOST_SITE_PACKAGES>")
            for path in [*site.getsitepackages(), site.getusersitepackages()]
        ),
        (str(Path(sys.base_prefix).resolve()), "<HOST_PREFIX>"),
        (str(Path(sys.prefix).resolve()), "<HOST_PREFIX>"),
    ]
    for host_path, placeholder in sorted(
        set(host_paths),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if host_path not in {"", "/"}:
            serialized = serialized.replace(host_path, placeholder)
    return json.loads(canonicalize_temporary_paths(serialized))


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    source_fingerprint = tree_fingerprint(ROOT)
    with tempfile.TemporaryDirectory(prefix="chronofin-cleanroom-") as directory:
        temporary_root = Path(directory)
        checkout = temporary_root / "checkout"
        venv = temporary_root / "venv"
        shutil.copytree(ROOT, checkout, ignore=_ignore)

        clean_env = dict(os.environ)
        for name in (
            "HY3_API_KEY", "HY3_BASE_URL", "HY3_MODEL", "OPENAI_API_KEY",
            "TOKENHUB_API_KEY", "CHATANYWHERE_API_KEY",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        ):
            clean_env.pop(name, None)
        clean_env["PYTHONPATH"] = str(checkout / "src")
        clean_env["PIP_NO_INDEX"] = "1"

        commands: list[tuple[str, list[str]]] = [
            ("create_venv", [sys.executable, "-m", "venv", "--system-site-packages", str(venv)]),
        ]
        results: list[dict[str, Any]] = []
        for label, command in commands:
            results.append(_run(label, command, checkout, clean_env))
            if results[-1]["exit_code"] != 0:
                break

        venv_python = venv / "bin" / "python"
        venv_cli = venv / "bin" / "chronofin"
        if results and results[-1]["exit_code"] == 0:
            followups = [
                (
                    "install_local_package",
                    [str(venv_python), "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", str(checkout)],
                ),
                ("compileall", [str(venv_python), "-m", "compileall", "-q", "src", "scripts", "tests", "app.py"]),
                ("unit_tests", [str(venv_python), "-m", "unittest", "discover", "-s", "tests", "-t", "."]),
                ("reprocess_saved_causal", [str(venv_python), "scripts/reprocess_saved_causal.py"]),
                ("offline_experiments", [str(venv_python), "scripts/run_offline_experiments.py"]),
                ("synthetic_benchmark", [str(venv_python), "scripts/run_synthetic_benchmark.py"]),
                ("evaluator_ablation", [str(venv_python), "scripts/run_evaluator_ablation.py"]),
                ("postfreeze_regression", [str(venv_python), "scripts/run_postfreeze_challenge.py"]),
                ("sanitize_public_artifacts", [str(venv_python), "scripts/sanitize_public_artifacts.py"]),
                (
                    "cli_inspect",
                    [
                        str(venv_cli), "inspect", "--manifest", "data/demo/manifest.json",
                        "--question", "云舟科技 FY2025 全年净利润是多少？", "--as-of", "2025-12-31",
                        "--entity", "云舟科技", "--period", "FY2025", "--top-k", "20",
                    ],
                ),
                ("git_init", ["git", "init", "-q"]),
                ("git_stage_submission", ["git", "add", "."]),
            ]
            for label, command in followups:
                result = _run(label, command, checkout, clean_env)
                results.append(result)
                if result["exit_code"] != 0:
                    break

        cached_pdfs = [
            path.relative_to(checkout).as_posix()
            for path in checkout.rglob("*.pdf")
            if "data/cache" in path.relative_to(checkout).as_posix()
        ]
        # The verifier consumes a complete proof of every prerequisite.  Its
        # own exit code is then appended to the final proof, avoiding a
        # logically circular requirement that a report prove its own check.
        report = _build_report(
            source_fingerprint=source_fingerprint,
            checkout=checkout,
            temporary_root=temporary_root,
            cached_pdfs=cached_pdfs,
            results=results,
        )
        provisional_output = checkout / "results" / "cleanroom_verification.json"
        _write_report(provisional_output, report)
        if report["all_passed"]:
            verifier_result = _run(
                "submission_verifier",
                [
                    str(venv_python),
                    "scripts/verify_submission.py",
                    "--compact",
                    "--cleanroom-prerequisites",
                ],
                checkout,
                clean_env,
            )
            verifier_result["verification_scope"] = (
                "all_submission_checks_except_cleanroom_self_check"
            )
            results.append(verifier_result)
        report = _build_report(
            source_fingerprint=source_fingerprint,
            checkout=checkout,
            temporary_root=temporary_root,
            cached_pdfs=cached_pdfs,
            results=results,
        )

    _write_report(OUTPUT, report)
    print(json.dumps({
        "output": str(OUTPUT),
        "all_passed": report["all_passed"],
        "commands": len(report["commands"]),
        "source_tree_sha256": source_fingerprint,
    }, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
