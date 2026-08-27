"""Small deterministic financial-metric ontology for stable proof-graph keys.

The model may propose a semantic key, but graph identity cannot depend on free
wording. This normalizer intentionally covers common statement metrics and
falls back to a conservative slug instead of guessing an accounting concept.
"""

from __future__ import annotations

import re

from .models import Claim


NON_WORD = re.compile(r"[^0-9a-zA-Z_\u3400-\u9fff]+")


def _metric_from(raw_key: str, text: str) -> str:
    raw = raw_key.lower().replace("-", "_")
    joined = raw + " " + text.lower()
    if any(marker in joined for marker in ("non_ifrs_profit_margin", "non-ifrs profit margin", "non ifrs profit margin")):
        return "non_ifrs_profit_margin"
    if any(marker in joined for marker in ("ifrs_profit_margin", "profit margin", "net_margin", "netmargin", "净利率")):
        return "ifrs_profit_margin" if "ifrs" in joined else "net_margin"
    if any(marker in joined for marker in ("non_ifrs_profit", "nonifrsprofit", "non-ifrs profit", "non ifrs profit")):
        return "non_ifrs_profit"
    if "ifrs" in joined and any(marker in joined for marker in ("profit attributable", "profit_attributable", "ifrsprofit")):
        return "ifrs_profit"
    if any(marker in joined for marker in ("profit_attributable", "profit attributable")):
        return "profit_attributable"
    if any(marker in joined for marker in ("net_margin", "netmargin", "净利率")):
        return "net_margin"
    if any(marker in joined for marker in ("net_profit", "netprofit", "净利润")):
        return "net_profit"
    if any(marker in joined for marker in ("revenue_driver", "growth_driver", "增长的主要驱动", "收入增长")) and any(
        marker in joined for marker in ("驱动", "driver")
    ):
        return "revenue_driver"
    if any(marker in joined for marker in ("revenue_risk", "收入波动风险")):
        return "revenue_risk"
    if any(marker in joined for marker in (
        "customer_concentration", "top5_customer", "top_5_customer", "客户集中", "前五大客户"
    )):
        return "customer_concentration"
    if any(marker in joined for marker in ("revenue", "营业收入", "营收")):
        return "revenue"
    pieces = raw_key.split(".")
    candidate = pieces[-2] if len(pieces) >= 3 else raw_key
    candidate = NON_WORD.sub("_", candidate).strip("_").lower()
    return candidate or "unspecified_metric"


def normalize_period(period: str) -> str:
    compact = re.sub(r"\s+", "", period).upper()
    compact = compact.replace("财年", "FY").replace("年度", "FY")
    return NON_WORD.sub("", compact) or "UNSPECIFIED"


def canonical_semantic_key(claim: Claim) -> str:
    entity = NON_WORD.sub("", claim.entity) or "unspecified_entity"
    metric = _metric_from(claim.semantic_key, claim.text)
    return f"{entity}.{metric}.{normalize_period(claim.period)}"
