from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "download_public_reports.py"
SPEC = importlib.util.spec_from_file_location("public_report_downloader", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublicReportDownloaderTests(unittest.TestCase):
    def test_pre_registered_snapshot_identity_is_required(self):
        content = b"%PDF-1.7\nreviewed fixture\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.pdf"
            path.write_bytes(content)
            item = {
                "id": "fixture",
                "expected_sha256": hashlib.sha256(content).hexdigest(),
                "expected_bytes": len(content),
            }
            self.assertEqual(
                MODULE.validate_snapshot(path, item),
                (item["expected_sha256"], len(content)),
            )

    def test_changed_bytes_fail_closed(self):
        reviewed = b"%PDF-1.7\nreviewed\n"
        changed = b"%PDF-1.7\nchanged upstream\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.pdf"
            path.write_bytes(changed)
            item = {
                "id": "fixture",
                "expected_sha256": hashlib.sha256(reviewed).hexdigest(),
                "expected_bytes": len(reviewed),
            }
            with self.assertRaisesRegex(RuntimeError, "Do not silently accept"):
                MODULE.validate_snapshot(path, item)

    def test_registry_pins_all_three_public_reports(self):
        import json

        registry = json.loads(
            (ROOT / "data" / "public" / "tencent_sources.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(registry["documents"]), 3)
        for item in registry["documents"]:
            self.assertRegex(item["expected_sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(item["expected_bytes"], 100_000)


if __name__ == "__main__":
    unittest.main()
