from __future__ import annotations

import unittest

from chronofin.models import Claim, ClaimType
from chronofin.ontology import canonical_semantic_key


def claim(raw_key: str, text: str, period: str = "FY2024") -> Claim:
    return Claim(
        id="C", text=text, claim_type=ClaimType.FACT, entity="云舟科技",
        period=period, unit="", known_at="2025-03-18", semantic_key=raw_key,
    )


class OntologyTests(unittest.TestCase):
    def test_customer_share_aliases_collapse(self):
        left = canonical_semantic_key(claim("云舟科技.top5_customer_revenue_share.FY2024", "前五大客户贡献收入的48%"))
        right = canonical_semantic_key(claim("云舟科技.customer_concentration.FY2024", "客户集中度为48%"))
        self.assertEqual(left, right)
        self.assertEqual(left, "云舟科技.customer_concentration.FY2024")

    def test_net_profit_and_margin_remain_distinct(self):
        profit = canonical_semantic_key(claim("company.netprofit.FY2024", "净利润144百万元"))
        margin = canonical_semantic_key(claim("company.netmargin.FY2024", "净利率12%"))
        self.assertNotEqual(profit, margin)

    def test_half_year_period_normalizes(self):
        value = canonical_semantic_key(claim("x.revenue.H12025", "上半年收入", "H1 2025"))
        self.assertTrue(value.endswith(".H12025"))


if __name__ == "__main__":
    unittest.main()

