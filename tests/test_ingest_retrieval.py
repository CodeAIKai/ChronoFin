from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from chronofin.ingest import _attach_table_context, extract_pages, load_manifest, sha256_file
from chronofin.models import Query, ValidationError
from chronofin.retrieval import BM25Retriever, detect_financial_slots, future_leak_count, tokenize

from .common import MANIFEST, corpus


class IngestRetrievalTests(unittest.TestCase):
    def test_manifest_has_three_documents(self):
        self.assertEqual(len(load_manifest(MANIFEST)), 3)

    def test_page_markers_are_preserved(self):
        pages = extract_pages(MANIFEST.parent / "cloud_2024.md")
        self.assertEqual(len(pages), 2)
        self.assertIn("营业收入", pages[0])
        self.assertIn("客户集中度", pages[1])

    def test_expected_chunk_ids_exist(self):
        _, chunks = corpus()
        self.assertIn("cloud_2024:p1:c1", chunks)
        self.assertIn("cloud_2024:p2:c5", chunks)

    def test_table_rows_inherit_period_header(self):
        blocks = [
            ("", "Year ended 31 December\n2025 2024\n(RMB in millions)"),
            ("", "Revenues 751,766 660,257"),
            ("", "Profit 224,842 194,073"),
        ]
        enriched = _attach_table_context(blocks)
        self.assertIn("2025 2024", enriched[1][1])
        self.assertIn("Revenues 751,766", enriched[1][1])

    def test_mixed_chinese_tokenization(self):
        tokens = tokenize("FY2024营业收入 1,200 百万元")
        self.assertIn("fy", tokens)
        self.assertIn("营业", tokens)
        self.assertIn("1,200", tokens)

    def test_temporal_filter_excludes_future_annual_report(self):
        documents, chunks = corpus()
        query = Query("2025财年全年净利润是多少", "2025-12-31", "云舟科技", "FY2025")
        audit = BM25Retriever(chunks.values()).search(query, documents, top_k=20)
        self.assertNotIn("cloud_2025_annual", audit.eligible_document_ids)
        self.assertTrue(all(hit.chunk.document_id != "cloud_2025_annual" for hit in audit.hits))
        self.assertEqual(future_leak_count(audit.hits, query.as_of_date), 0)

    def test_ablation_can_expose_future_source(self):
        documents, chunks = corpus()
        query = Query("2025财年全年净利润是多少", "2025-12-31", "云舟科技", "FY2025")
        audit = BM25Retriever(chunks.values()).search(query, documents, top_k=20, temporal_filter=False)
        self.assertIn("cloud_2025_annual", audit.eligible_document_ids)
        self.assertGreater(future_leak_count(audit.hits, query.as_of_date), 0)

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValidationError):
            Query("question", "2025/12/31")

    def test_margin_query_reserves_numerator_and_denominator_slots(self):
        slots = detect_financial_slots("What are revenue, profit attributable and the derived profit margin?")
        self.assertIn("revenue", slots)
        self.assertIn("profit_attributable", slots)
        self.assertNotIn("net_profit", slots)

    def test_canonical_semantic_keys_preserve_metric_slots(self):
        slots = detect_financial_slots(
            "apple.gaap_net_income.FY2024 apple.gaap_net_income_margin.FY2024"
        )
        self.assertIn("net_profit", slots)
        self.assertIn("profit_margin", slots)

    def test_attributable_profit_semantic_key_is_detected(self):
        slots = detect_financial_slots("TencentHoldingsLimited.profit_attributable.FY2025")
        self.assertIn("profit_attributable", slots)

    def test_slot_retrieval_contains_revenue_and_profit(self):
        documents, chunks = corpus()
        query = Query("营业收入、归属于股东的净利润和净利率", "2025-12-31", "云舟科技", "FY2024")
        audit = BM25Retriever(chunks.values()).search(query, documents, top_k=5)
        slot_map = dict(audit.slot_hits)
        self.assertIn("revenue", slot_map)
        self.assertTrue("profit_attributable" in slot_map or "net_profit" in slot_map)

    def test_prior_year_and_interim_do_not_fill_target_full_year_slots(self):
        documents, chunks = corpus()
        query = Query("FY2025全年净利润是多少", "2025-12-31", "云舟科技", "FY2025")
        audit = BM25Retriever(chunks.values()).search(query, documents, top_k=20)
        self.assertIn("net_profit", audit.uncovered_slots)
        self.assertIn("full_year", audit.uncovered_slots)
        self.assertNotIn("net_profit", dict(audit.slot_hits))
        self.assertNotIn("full_year", dict(audit.slot_hits))
        self.assertTrue(any(hit.chunk.period == "H1 2025" for hit in audit.hits))

    def test_slots_unlock_after_target_annual_report_is_published(self):
        documents, chunks = corpus()
        query = Query("FY2025全年净利润是多少", "2026-03-21", "云舟科技", "FY2025")
        audit = BM25Retriever(chunks.values()).search(query, documents, top_k=20)
        self.assertNotIn("net_profit", audit.uncovered_slots)
        self.assertNotIn("full_year", audit.uncovered_slots)
        self.assertTrue(dict(audit.slot_hits)["net_profit"].startswith("cloud_2025_annual:"))

    def test_duplicate_document_id_rejected(self):
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        payload["documents"].append(dict(payload["documents"][0]))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manifest.json"
            # Repoint paths to absolute originals so the duplicate-id check is isolated.
            for item in payload["documents"]:
                item["path"] = str(MANIFEST.parent / item["path"])
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_manifest(target)


if __name__ == "__main__":
    unittest.main()
