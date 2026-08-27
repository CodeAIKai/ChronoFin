from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from chronofin.config import RetrievalConfig
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.llm import LLMError, LLMTrace, parse_json_object
from chronofin.models import Answerability, ClaimType, Query
from chronofin.pipeline import (
    ChronoFinPipeline,
    _expand_exact_quote,
    _replace_rendered_number,
    _synchronize_derived_claim_text,
)
from chronofin.render import render_html, write_html

from .common import MANIFEST, good_answer


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, system, user):
        return self.payload, LLMTrace("fake-hy3", "local", "hash", 0.001)


class PipelineRenderTests(unittest.TestCase):
    def test_json_fence_parser(self):
        self.assertEqual(parse_json_object("```json\n{\"ok\": true}\n```"), {"ok": True})

    def test_truncated_json_is_rejected_not_silently_repaired(self):
        with self.assertRaises(LLMError):
            parse_json_object('{"claims": [{"id": "C1"}')

    def test_trace_serialization_hashes_provider_request_id(self):
        trace = LLMTrace("hy3", "local", "prompt", 0.1, request_id="provider-private-id")
        payload = trace.to_dict()
        self.assertNotIn("request_id", payload)
        self.assertRegex(payload["request_id_sha256"], r"^[0-9a-f]{64}$")

    def test_bare_table_number_expands_to_exact_row_context(self):
        source = "Year ended 31 December 2025\nRevenues 751,766 660,257\nCost of revenues 329,173"
        expanded = _expand_exact_quote(source, "751,766")
        self.assertIn("Revenues 751,766", expanded)
        self.assertIn(expanded, source)

    def test_long_mid_sentence_quote_expands_to_metric_name(self):
        source = (
            "Profit attributable to equity holders of the Company increased by 16%\n"
            "year-on-year to RMB224.8 billion for the year ended 31 December 2025. "
            "Non-IFRS profit was RMB259.6 billion."
        )
        quote = "RMB224.8 billion for the year ended 31 December 2025"
        expanded = _expand_exact_quote(source, quote)
        self.assertIn("Profit attributable to equity holders", expanded)
        self.assertIn(expanded, source)

    def test_non_exact_quote_is_never_auto_repaired(self):
        self.assertEqual(_expand_exact_quote("Revenue 100", "Revenue 101"), "Revenue 101")

    def test_audited_result_replaces_same_precision_model_number(self):
        self.assertEqual(
            _replace_rendered_number("derived margin = 29.9073%.", 29.9073, 29.90292191985272),
            "derived margin = 29.9029%.",
        )

    def test_derived_text_sync_changes_only_explicit_terminal_result(self):
        text = "224,800 / 751,766 = 29.9073%."
        self.assertEqual(
            _synchronize_derived_claim_text(text, 29.90292191985272, "%"),
            "224,800 / 751,766 = 29.9029%.",
        )

    def test_derived_text_sync_refuses_ambiguous_prose(self):
        text = "利润率较上年有所改善，参考收入 751,766。"
        self.assertEqual(_synchronize_derived_claim_text(text, 29.9, "%"), text)

    def test_pipeline_rebinds_source_metadata(self):
        payload = {
            "answerability": "answerable",
            "executive_summary": "收入已披露。",
            "evidence": [{"id": "E1", "chunk_id": "cloud_2024:p1:c1", "quote": "云舟科技 2024 财年营业收入为 1,200 百万元"}],
            "calculations": [],
            "claims": [{
                "id": "C1", "text": "云舟科技 2024 财年营业收入为 1,200 百万元。", "claim_type": "FACT",
                "entity": "云舟科技", "period": "FY2024", "unit": "百万元", "known_at": "2099-01-01",
                "evidence_ids": ["E1"], "confidence": 0.9, "semantic_key": "cloud.revenue.FY2024"
            }],
            "caveats": []
        }
        pipeline = ChronoFinPipeline(MANIFEST, FakeClient(payload), RetrievalConfig(top_k=20))
        answer = pipeline.run(Query("FY2024营业收入", "2025-12-31", "云舟科技", "FY2024"))
        self.assertEqual(answer.evidence[0].published_at, "2025-03-18")
        self.assertEqual(answer.claims[0].known_at, "2025-03-18")
        self.assertNotEqual(answer.claims[0].known_at, "2099-01-01")

    def test_pipeline_preserves_unknown_citation_for_audit(self):
        payload = {
            "answerability": "answerable", "executive_summary": "错误引用", "calculations": [], "claims": [], "caveats": [],
            "evidence": [{"id": "E404", "chunk_id": "invented:p99:c9", "quote": "不存在"}],
        }
        pipeline = ChronoFinPipeline(MANIFEST, FakeClient(payload), RetrievalConfig(top_k=20))
        answer = pipeline.run(Query("FY2024营业收入", "2025-12-31", "云舟科技", "FY2024"))
        self.assertEqual(answer.evidence[0].document_id, "__unknown__")
        self.assertTrue(answer.provenance["schema_warnings"])

    def test_stale_chunk_id_rebinds_only_by_unique_exact_quote(self):
        payload = {
            "answerability": "answerable", "executive_summary": "收入", "calculations": [], "claims": [], "caveats": [],
            "evidence": [{
                "id": "E1", "chunk_id": "old:p1:c999", "document_id": "cloud_2024", "page": 1,
                "quote": "云舟科技 2024 财年营业收入为 1,200 百万元"
            }],
        }
        pipeline = ChronoFinPipeline(MANIFEST, FakeClient(payload), RetrievalConfig(top_k=20))
        answer = pipeline.run(Query("FY2024营业收入", "2025-12-31", "云舟科技", "FY2024"))
        self.assertEqual(answer.evidence[0].chunk_id, "cloud_2024:p1:c1")
        self.assertIn("stale chunk id rebound", answer.provenance["schema_warnings"][0])

    def test_future_document_never_enters_prompt(self):
        class InspectClient(FakeClient):
            def complete_json(self, system, user):
                self.user = user
                return super().complete_json(system, user)
        client = InspectClient({"answerability": "unanswerable", "executive_summary": "不可知", "evidence": [], "claims": [], "calculations": [], "caveats": []})
        pipeline = ChronoFinPipeline(MANIFEST, client, RetrievalConfig(top_k=20))
        pipeline.run(Query("FY2025全年结果", "2025-12-31", "云舟科技", "FY2025"))
        self.assertNotIn("1,680", client.user)
        self.assertNotIn("252", client.user)

    def test_no_hit_path_emits_query_aligned_unknown_claim(self):
        client = FakeClient({})
        pipeline = ChronoFinPipeline(MANIFEST, client, RetrievalConfig(top_k=20))
        answer = pipeline.run(Query("FY2024营业收入", "2020-01-01", "云舟科技", "FY2024"))
        self.assertEqual(answer.answerability, Answerability.UNANSWERABLE)
        self.assertEqual(len(answer.claims), 1)
        self.assertEqual(answer.claims[0].claim_type, ClaimType.UNKNOWN)
        self.assertEqual(answer.claims[0].entity, "云舟科技")
        self.assertEqual(answer.claims[0].period, "FY2024")
        self.assertFalse(answer.provenance["model_called"])
        score = ChronoFinEvaluator().evaluate(
            answer,
            pipeline.chunk_index,
            expected_answerability=Answerability.UNANSWERABLE,
        )
        self.assertEqual(score.final_score, 100)
        self.assertIsNone(score.hard_cap)

    def test_html_escapes_untrusted_text(self):
        answer = good_answer()
        answer.executive_summary = "<script>alert(1)</script>"
        rendered = render_html(answer)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_html_allows_https_but_blocks_script_source_links(self):
        answer = good_answer()
        answer.evidence[0] = replace(answer.evidence[0], source_url="https://example.com/report.pdf")
        self.assertIn("href='https://example.com/report.pdf'", render_html(answer))
        answer.evidence[0] = replace(answer.evidence[0], source_url="javascript:alert(1)")
        rendered = render_html(answer)
        self.assertNotIn("href='javascript:", rendered)

    def test_html_file_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.html"
            write_html(good_answer(), target)
            self.assertTrue(target.exists())
            self.assertIn("ChronoFin", target.read_text(encoding="utf-8"))

    def test_html_exposes_deterministic_correction_log(self):
        answer = good_answer()
        answer.provenance["claim_text_corrections"] = [{
            "claim_id": "C3", "original_text": "净利率13%", "corrected_text": "净利率12%"
        }]
        rendered = render_html(answer)
        self.assertIn("确定性修正日志", rendered)
        self.assertIn("净利率13%", rendered)


if __name__ == "__main__":
    unittest.main()
