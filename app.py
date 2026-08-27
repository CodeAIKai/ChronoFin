"""Streamlit demo for ChronoFin. Install with: pip install -e '.[demo]'"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover - UI dependency is optional
    raise SystemExit("Streamlit is optional. Run: pip install -e '.[demo]' && streamlit run app.py") from exc

from chronofin.config import Hy3Config, RetrievalConfig
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.evaluator.mutations import DEFAULT_CONTRAST_MUTATIONS, run_contrast_suite
from chronofin.ingest import ingest_manifest
from chronofin.llm import ChatCompletionsClient
from chronofin.models import Query
from chronofin.pipeline import ChronoFinPipeline
from chronofin.render import load_answer, render_html


st.set_page_config(page_title="ChronoFin 时证", page_icon="⏱️", layout="wide")
st.title("ChronoFin · 时证")
st.caption("可反事实审计的时点金融研究助手｜Hy3 + 类型化证明图 + 因果变形评估")

mode = st.sidebar.radio("运行方式", ["离线金标演示", "调用 Hy3"], help="API Key 只从 HY3_API_KEY 环境变量读取。")
offline_mode = mode == "离线金标演示"
manifest = st.sidebar.text_input(
    "文档清单",
    str(ROOT / "data" / "demo" / "manifest.json"),
    disabled=offline_mode,
    help="离线金标与固定 manifest 成对冻结；调用 Hy3 时可换成自己的 manifest。",
)
as_of = st.sidebar.date_input(
    "信息截止日",
    value=__import__("datetime").date(2025, 12, 31),
    disabled=offline_mode,
).isoformat()
entity = st.sidebar.text_input("分析实体", "云舟科技", disabled=offline_mode)
period = st.sidebar.text_input("目标期间", "FY2024", disabled=offline_mode)
question = st.text_area(
    "研究问题",
    "截至2025-12-31，云舟科技FY2024收入、净利润及净利率是多少？并说明主要驱动与风险。",
    height=90,
    disabled=offline_mode,
)
if offline_mode:
    st.info("离线模式回放固定金标，输入已锁定以避免看似修改但输出不变；切换到“调用 Hy3”即可使用自定义问题。")

if "answer" not in st.session_state:
    st.session_state.answer = None
    st.session_state.score = None
    st.session_state.chunks = None

if st.button("开始时点分析", type="primary", use_container_width=True):
    with st.spinner("过滤未来材料、检索证据并构建证明图…"):
        if mode == "离线金标演示":
            answer = load_answer(ROOT / "data" / "demo" / "fixtures" / "good.json")
            _, chunks = ingest_manifest(manifest)
            chunk_index = {chunk.id: chunk for chunk in chunks}
        else:
            pipeline = ChronoFinPipeline(manifest, ChatCompletionsClient(Hy3Config.from_env()), RetrievalConfig(top_k=12))
            answer = pipeline.run(Query(question, as_of, entity, period))
            chunk_index = pipeline.chunk_index
        score = ChronoFinEvaluator().evaluate(
            answer,
            chunk_index,
            expected_answerability=answer.answerability if offline_mode else None,
        )
        st.session_state.answer, st.session_state.score, st.session_state.chunks = answer, score, chunk_index

answer = st.session_state.answer
score = st.session_state.score
if answer is not None:
    metrics = st.columns(4)
    metrics[0].metric("审计总分", f"{score.final_score:.1f}")
    metrics[1].metric("结论", score.verdict.upper())
    metrics[2].metric("证据条数", len(answer.evidence))
    metrics[3].metric("截止日后材料隔离", len(answer.excluded_documents))

    overview, ledger, audit_tab, stress = st.tabs(["研究结论", "证明账本", "质量审计", "红队变形"])
    with overview:
        st.subheader(answer.executive_summary)
        if answer.caveats:
            st.warning("；".join(answer.caveats))
        st.markdown("#### 时间隔离日志")
        st.json(answer.excluded_documents, expanded=False)
    with ledger:
        st.markdown("#### 原子结论")
        st.dataframe([{
            "id": item.id, "type": item.claim_type.value, "claim": item.text,
            "entity": item.entity, "period": item.period, "unit": item.unit,
            "known_at": item.known_at, "value": item.value, "evidence": ",".join(item.evidence_ids), "confidence": item.confidence,
        } for item in answer.claims], use_container_width=True, hide_index=True)
        st.markdown("#### 计算血缘")
        st.json([{
            "id": item.id, "expression": item.expression, "result": item.result,
            "unit": item.unit, "operands": [op.__dict__ for op in item.operands]
        } for item in answer.calculations], expanded=True)
        st.markdown("#### 精确证据")
        for item in answer.evidence:
            with st.expander(f"{item.id} · {item.document_id} · p.{item.page} · {item.published_at}"):
                st.write(item.quote)
                st.code(item.chunk_id)
    with audit_tab:
        st.dataframe([{
            "dimension": item.name, "score": item.score, "weight": item.weight,
            "method": item.method, "issues": "; ".join(item.issues)
        } for item in score.dimensions], use_container_width=True, hide_index=True)
        if score.hard_gate_reasons:
            st.error("硬门禁：" + "；".join(score.hard_gate_reasons))
        else:
            st.success("未触发硬门禁")
        correction_log = {
            key: answer.provenance.get(key, [])
            for key in ("calculation_corrections", "claim_text_corrections", "citation_normalizations")
            if answer.provenance.get(key)
        }
        if correction_log:
            with st.expander("确定性修正日志", expanded=True):
                st.json(correction_log)
        st.caption("聚合分不能抵消未来泄漏、伪引用或实质数值错误。")
    with stress:
        if st.button(f"运行 {len(DEFAULT_CONTRAST_MUTATIONS)} 类受控变形"):
            result = run_contrast_suite(answer, st.session_state.chunks)
            a, b, c = st.columns(3)
            a.metric("判别准确率 PDA", f"{result['paired_discrimination_accuracy']:.0%}")
            b.metric("不变违规率 IVR", f"{result['invariance_violation_rate']:.0%}")
            c.metric("严重度相关", f"{result['severity_drop_spearman']:.3f}")
            st.dataframe(result["results"], use_container_width=True, hide_index=True)
    html_report = render_html(answer, score)
    st.download_button("下载可审计 HTML 报告", html_report, "chronofin_report.html", "text/html")
