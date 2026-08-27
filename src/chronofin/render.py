"""Dependency-free JSON and HTML result rendering."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .models import AnalysisAnswer


def write_json(value: Any, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = value.to_dict() if hasattr(value, "to_dict") else value
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_answer(path: str | Path) -> AnalysisAnswer:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return AnalysisAnswer.from_dict(payload)


def render_html(answer: AnalysisAnswer, scorecard: Any | None = None, title: str = "ChronoFin 时证") -> str:
    score_payload = scorecard.to_dict() if hasattr(scorecard, "to_dict") else scorecard
    score = score_payload.get("final_score") if isinstance(score_payload, dict) else None
    verdict = score_payload.get("verdict", "") if isinstance(score_payload, dict) else ""

    def esc(value: Any) -> str:
        return html.escape(str(value))

    def source_link(value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return f" · <a href='{html.escape(value, quote=True)}' target='_blank' rel='noopener noreferrer'>官方来源</a>"

    claim_rows = "".join(
        f"<tr><td>{esc(claim.id)}</td><td><span class='tag {claim.claim_type.value.lower()}'>{esc(claim.claim_type.value)}</span></td>"
        f"<td>{esc(claim.text)}</td><td>{esc(claim.entity)}</td><td>{esc(claim.period)}</td>"
        f"<td>{esc(claim.unit)}</td><td>{esc(', '.join(claim.evidence_ids))}</td><td>{claim.confidence:.2f}</td></tr>"
        for claim in answer.claims
    ) or "<tr><td colspan='8' class='muted'>无原子结论；系统选择拒答。</td></tr>"
    evidence_cards = "".join(
        f"<article><div class='e-head'><b>{esc(item.id)}</b> · {esc(item.document_id)} · p.{item.page} · 公布 {esc(item.published_at)}{source_link(item.source_url)}</div>"
        f"<blockquote>{esc(item.quote)}</blockquote><div class='mono'>{esc(item.chunk_id)}</div></article>"
        for item in answer.evidence
    ) or "<p class='muted'>没有使用证据。</p>"
    excluded = "".join(
        f"<li><b>{esc(item.get('title', item.get('document_id', '')))}</b> — {esc(item.get('reason', ''))}</li>"
        for item in answer.excluded_documents
    ) or "<li>无</li>"
    calc_cards_list: list[str] = []
    for calc in answer.calculations:
        operands = "".join(
            "<li>{}={} {} ← {}</li>".format(
                esc(op.name), esc(op.value), esc(op.unit),
                esc(", ".join([*op.evidence_ids, *(f"calc:{item}" for item in op.calculation_ids)]))
            )
            for op in calc.operands
        )
        calc_cards_list.append(
            f"<article><div class='e-head'><b>{esc(calc.id)}</b> · {esc(calc.unit)}</div>"
            f"<div class='formula'>{esc(calc.expression)} = {esc(calc.result)}</div>"
            f"<ul>{operands}</ul></article>"
        )
    calc_cards = "".join(calc_cards_list) or "<p class='muted'>本次回答无派生计算。</p>"
    dimension_rows = ""
    gates = ""
    correction_payload = {
        key: answer.provenance.get(key, [])
        for key in ("calculation_corrections", "claim_text_corrections", "citation_normalizations")
        if answer.provenance.get(key)
    }
    correction_section = (
        "<h2>确定性修正日志</h2><div class='card'><pre class='audit-log'>"
        + esc(json.dumps(correction_payload, ensure_ascii=False, indent=2))
        + "</pre></div>"
        if correction_payload else ""
    )
    if isinstance(score_payload, dict):
        dimension_rows = "".join(
            f"<tr><td>{esc(item['name'])}</td><td>{float(item['score']):.1f}</td><td>{float(item['weight']):.0%}</td>"
            f"<td>{esc('; '.join(item.get('issues', [])))}</td></tr>"
            for item in score_payload.get("dimensions", [])
        )
        gates = "".join(f"<li>{esc(item)}</li>" for item in score_payload.get("hard_gate_reasons", [])) or "<li>未触发硬门禁</li>"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>
:root{{--ink:#12212f;--muted:#607080;--paper:#f5f7f4;--card:#fff;--cyan:#0b7d83;--gold:#bd7b16;--red:#b42a36;--line:#dbe3df}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
header{{background:linear-gradient(120deg,#102f38,#0b6168);color:white;padding:34px max(5vw,24px)}}h1{{margin:0 0 5px;font-size:30px}}header p{{margin:0;opacity:.84}}
main{{max-width:1240px;margin:0 auto;padding:24px}}.hero{{display:grid;grid-template-columns:2fr 1fr;gap:18px}}.card,article{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:0 4px 18px #102f380d;margin-bottom:16px}}
.score{{font-size:45px;font-weight:750;color:var(--cyan)}}.verdict{{text-transform:uppercase;letter-spacing:.12em;color:var(--gold)}}h2{{margin:28px 0 12px;font-size:20px}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#eaf1ee;font-size:13px}}
.tag{{font-size:11px;border:1px solid;padding:3px 6px;border-radius:99px}}.derived{{color:#7a4d00}}.unknown{{color:var(--red)}}.muted{{color:var(--muted)}}blockquote{{border-left:3px solid var(--cyan);margin:12px 0;padding:7px 12px;background:#f5faf9}}.e-head{{color:var(--muted)}}.mono,.formula,.audit-log{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px}}.formula{{background:#102f38;color:white;padding:10px;border-radius:7px}}.audit-log{{white-space:pre-wrap;overflow-wrap:anywhere}}
.timeline li::marker{{color:var(--red)}}@media(max-width:800px){{.hero{{grid-template-columns:1fr}}.table-wrap{{overflow:auto}}}}
</style></head><body><header><h1>{esc(title)}</h1><p>每个结论都回答：当时知道吗？证据在哪？证据改变时结论会跟着变吗？</p></header><main>
<section class="hero"><div class="card"><div class="muted">问题 · 截止 {esc(answer.query.as_of_date)}</div><h2>{esc(answer.query.question)}</h2><p>{esc(answer.executive_summary)}</p><span class="tag">{esc(answer.answerability.value)}</span></div>
<div class="card"><div class="muted">审计总分</div><div class="score">{esc(f'{score:.1f}' if isinstance(score,(int,float)) else '—')}</div><div class="verdict">{esc(verdict or 'not evaluated')}</div></div></section>
<h2>原子结论账本</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>类型</th><th>命题</th><th>实体</th><th>期间</th><th>单位</th><th>证据</th><th>置信</th></tr></thead><tbody>{claim_rows}</tbody></table></div>
<h2>计算血缘</h2>{calc_cards}<h2>证据卡片</h2>{evidence_cards}
<h2>时间隔离日志</h2><div class="card"><ul class="timeline">{excluded}</ul></div>
{correction_section}
{f'<h2>十维质量审计</h2><div class="table-wrap"><table><thead><tr><th>维度</th><th>分数</th><th>权重</th><th>问题</th></tr></thead><tbody>{dimension_rows}</tbody></table></div><h2>硬门禁</h2><div class="card"><ul>{gates}</ul></div>' if score_payload else ''}
</main></body></html>"""


def write_html(answer: AnalysisAnswer, path: str | Path, scorecard: Any | None = None) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(answer, scorecard), encoding="utf-8")
    return target
