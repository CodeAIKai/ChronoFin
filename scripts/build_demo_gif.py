#!/usr/bin/env python3
"""Build the sub-two-minute offline demo GIF from frozen experiment JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - optional presentation dependency
    raise SystemExit("Install demo dependencies first: python -m pip install -e '.[demo]'") from exc


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1280, 720
BG = "#071522"
PANEL = "#10283a"
PANEL_2 = "#153448"
TEXT = "#ecf7f5"
MUTED = "#9eb8bd"
TEAL = "#41d6c3"
GREEN = "#75e6a6"
AMBER = "#ffcb69"
RED = "#ff7b7b"
BLUE = "#77bdfb"
FONT_PATH = Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")


def load_json(relative: str) -> dict[str, Any]:
    payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{relative} must contain a JSON object")
    return payload


def font(size: int):
    if not FONT_PATH.exists():
        raise SystemExit(f"Chinese font not found: {FONT_PATH}")
    return ImageFont.truetype(str(FONT_PATH), size=size)


def wrap(draw: ImageDraw.ImageDraw, text: str, face, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and draw.textbbox((0, 0), candidate, font=face)[2] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines


def text_block(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    size: int,
    color: str = TEXT,
    max_width: int = 1120,
    spacing: int = 8,
) -> int:
    face = font(size)
    x, y = xy
    line_height = size + spacing
    for line in wrap(draw, value, face, max_width):
        draw.text((x, y), line, font=face, fill=color)
        y += line_height
    return y


def base_frame(step: int, title: str, kicker: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 34, 1232, 104), radius=22, fill=PANEL)
    draw.ellipse((72, 53, 104, 85), outline=TEAL, width=4)
    draw.line((88, 69, 88, 58), fill=TEAL, width=3)
    draw.line((88, 69, 98, 74), fill=TEAL, width=3)
    draw.text((122, 48), "ChronoFin · 时证", font=font(30), fill=TEXT)
    draw.text((970, 52), f"{step}/8  {kicker}", font=font(20), fill=MUTED)
    draw.text((62, 130), title, font=font(42), fill=TEXT)
    draw.rounded_rectangle((62, 687, 1218, 697), radius=5, fill="#1d4050")
    draw.rounded_rectangle((62, 687, 62 + int(1156 * step / 8), 697), radius=5, fill=TEAL)
    draw.text((62, 654), "冻结结果离线回放 · 不联网 · 不读取 API Key · 个人活动作品，非腾讯官方发布", font=font(17), fill=MUTED)
    return image, draw


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], heading: str, accent: str = TEAL) -> None:
    draw.rounded_rectangle(box, radius=22, fill=PANEL, outline="#225066", width=2)
    x1, y1, _, _ = box
    draw.rounded_rectangle((x1 + 22, y1 + 20, x1 + 30, y1 + 58), radius=4, fill=accent)
    draw.text((x1 + 48, y1 + 20), heading, font=font(25), fill=TEXT)


def metric(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, color: str = TEAL) -> None:
    draw.rounded_rectangle((x, y, x + 250, y + 112), radius=18, fill=PANEL_2)
    draw.text((x + 18, y + 15), label, font=font(18), fill=MUTED)
    draw.text((x + 18, y + 48), value, font=font(35), fill=color)


def build_frames() -> tuple[list[Image.Image], list[int]]:
    before = load_json("results/public_tencent_before_publication_final.json")
    after = load_json("results/public_tencent_after_publication_final.json")
    before_score = load_json("results/public_tencent_before_publication_final_score.json")
    after_score = load_json("results/public_tencent_after_publication_final_score.json")
    benchmark = load_json("results/synthetic_benchmark.json")
    ablation = load_json("results/evaluator_ablation.json")
    causal = load_json("results/live_causal_experiment_current.json")
    stability = load_json("results/public_tencent_current_deterministic_stability.json")
    challenge = load_json("results/postfreeze_challenge_v1_current_regression_after_slot_fix.json")
    corrections = after.get("provenance", {}).get("claim_text_corrections", [])
    if not stability.get("all_exact_scorecard_agreement") or not stability.get("all_scores_excellent"):
        raise ValueError("current Tencent deterministic stability check is not fully passing")
    if not challenge.get("summary", {}).get("all_passed"):
        raise ValueError("current regression challenge is not fully passing")

    frames: list[Image.Image] = []

    image, draw = base_frame(1, "财报答案不只要“像对”", "问题")
    text_block(draw, (80, 215), "当时知道吗？证据在哪里？证据改变时，结论真的会跟着变吗？", 35, TEAL, 1100, 13)
    card(draw, (80, 355, 1200, 590), "三段式可反驳承诺")
    text_block(draw, (118, 435), "Point-in-time 可知性边界   →   Typed proof graph   →   Causal metamorphic evaluation", 28, TEXT, 1030, 14)
    text_block(draw, (118, 510), "Hy3 负责阅读与解释；确定性层负责时间、身份、引文、公式和拒答门禁。", 23, MUTED, 1030)
    frames.append(image)

    image, draw = base_frame(2, "同一问题，只改截止日", "设问")
    card(draw, (70, 190, 1210, 520), "研究问题")
    text_block(draw, (112, 275), "腾讯 FY2025 全年收入、IFRS / non-IFRS 归母利润及利润率是多少？", 34, TEXT, 1030, 14)
    draw.rounded_rectangle((110, 400, 545, 475), radius=18, fill="#223f4e", outline=AMBER, width=2)
    draw.text((142, 420), "截止 2025-12-31", font=font(27), fill=AMBER)
    draw.rounded_rectangle((715, 400, 1150, 475), radius=18, fill="#163d3a", outline=GREEN, width=2)
    draw.text((757, 420), "截止 2026-04-10", font=font(27), fill=GREEN)
    draw.line((547, 438, 710, 438), fill=MUTED, width=3)
    draw.polygon(((700, 429), (715, 438), (700, 447)), fill=MUTED)
    text_block(draw, (120, 552), "检索前先按 published_at 隔离材料；未来文档永远不会进入 Hy3 提示词。", 23, MUTED, 1040)
    frames.append(image)

    image, draw = base_frame(3, "披露前：拒绝猜测", "时点 A")
    metric(draw, 72, 200, "Answerability", str(before.get("answerability", "")), AMBER)
    metric(draw, 345, 200, "确定性评分", f"{before_score['final_score']:.0f}", GREEN)
    metric(draw, 618, 200, "UNKNOWN claims", str(len(before.get("claims", []))), BLUE)
    metric(draw, 891, 200, "未来材料隔离", str(len(before.get("excluded_documents", []))), RED)
    card(draw, (72, 338, 1208, 610), "为什么不是“空拒答”")
    text_block(draw, (112, 415), "已有材料只覆盖中期；3 条 UNKNOWN 结论绑定 E1 / E2，并在 registry 中核验未来年报的真实发布日期。", 25, TEXT, 1030, 12)
    excluded = before.get("excluded_documents", [{}])[0]
    text_block(draw, (112, 510), f"隔离：{excluded.get('document_id', 'future annual report')} · published_at={excluded.get('published_at', '')}", 22, RED, 1030)
    text_block(draw, (112, 558), "当前门禁重复 5 次：均为 100 分，scorecard 哈希完全一致。", 20, GREEN, 1030)
    frames.append(image)

    image, draw = base_frame(4, "披露后：答案自动解锁", "时点 B")
    claims = {item["id"]: item for item in after.get("claims", [])}
    values = [
        ("营业收入", f"RMB {claims.get('C1', {}).get('value', 0):,.0f}m", TEAL),
        ("IFRS 归母利润", "RMB 224,800m", BLUE),
        ("IFRS 利润率", f"{claims.get('C4', {}).get('value', 0):.4f}%", GREEN),
        ("non-IFRS 利润率", f"{claims.get('C5', {}).get('value', 0):.4f}%", GREEN),
    ]
    for index, (label, value, color) in enumerate(values):
        metric(draw, 72 + index * 273, 196, label, value, color)
    card(draw, (72, 340, 1208, 610), "同一份答案的三重一致性")
    text_block(draw, (112, 410), "精确表头与页码  →  typed value  →  受限算式执行结果", 29, TEXT, 1030, 12)
    text_block(draw, (112, 482), "文案数字、结构化数值和执行器必须一致；聚合高分不能覆盖任一重大错误。", 24, MUTED, 1030, 12)
    draw.text((1040, 548), f"SCORE {after_score['final_score']:.0f}", font=font(29), fill=GREEN, anchor="ra")
    frames.append(image)

    image, draw = base_frame(5, "证明图：每条结论都承诺依赖", "血缘")
    nodes = [
        (95, 220, 285, 305, "E1 / E2", "精确原文", BLUE),
        (385, 180, 610, 265, "C1 / C2 / C3", "来源事实", TEAL),
        (385, 355, 610, 440, "CALC1", "224.8 × 1000", AMBER),
        (720, 250, 945, 335, "CALC2 / CALC3", "利润 ÷ 收入 × 100", AMBER),
        (1035, 220, 1200, 390, "C4 / C5", "29.9029%\n34.5355%", GREEN),
    ]
    for x1, y1, x2, y2, label, detail, color in nodes:
        draw.rounded_rectangle((x1, y1, x2, y2), radius=18, fill=PANEL, outline=color, width=3)
        draw.text(((x1 + x2) // 2, y1 + 17), label, font=font(24), fill=color, anchor="ma")
        text_block(draw, (x1 + 16, y1 + 49), detail, 18, TEXT, x2 - x1 - 32, 5)
    arrows = [((285, 262), (385, 222)), ((500, 265), (500, 355)), ((610, 398), (720, 294)), ((610, 222), (720, 278)), ((945, 294), (1035, 300))]
    for start, end in arrows:
        draw.line((*start, *end), fill=MUTED, width=4)
        draw.ellipse((end[0] - 5, end[1] - 5, end[0] + 5, end[1] + 5), fill=MUTED)
    text_block(draw, (96, 520), "改一个证据叶节点，只允许图后代改变；无关结论必须保持稳定。", 25, MUTED, 1080)
    frames.append(image)

    image, draw = base_frame(6, "红队发现漏洞，门禁必须响应", "失败→修复")
    card(draw, (70, 190, 600, 585), "保存的历史 Hy3 文案冲突", RED)
    numeric_corrections = [
        item for item in corrections
        if item.get("calculation_id") and not item.get("projection_kind")
    ]
    original_lines = [item.get("original_text", "").split("=")[-1].strip() for item in numeric_corrections]
    corrected_lines = [item.get("corrected_text", "").split("=")[-1].strip() for item in numeric_corrections]
    text_block(draw, (110, 270), "模型原文：" + " / ".join(original_lines), 24, RED, 450, 10)
    text_block(draw, (110, 360), "安全执行：" + " / ".join(corrected_lines), 24, GREEN, 450, 10)
    text_block(draw, (110, 465), "模型只产生候选；确定性层执行算式、投影正确结果，并保留可审计修正轨迹。", 20, MUTED, 450, 8)
    card(draw, (640, 190, 1210, 585), "拒答攻击", AMBER)
    text_block(draw, (680, 270), "空答案 / 一律拒答 / 结构化错误拒答", 25, TEXT, 490, 10)
    draw.text((680, 350), "旧版  93–100", font=font(30), fill=RED)
    draw.text((680, 408), "新版  ≤ 20", font=font(36), fill=GREEN)
    text_block(draw, (680, 485), "需匹配 answerability oracle，或给出可核验负面证据与未来隔离记录。", 20, MUTED, 470)
    frames.append(image)

    image, draw = base_frame(7, "不是只在一个成功样例上自洽", "评测")
    coverage = benchmark["coverage"]
    metrics = benchmark["metrics"]
    metric(draw, 72, 190, "形式化原题", str(coverage["base_tasks"]), BLUE)
    metric(draw, 345, 190, "相关变异", f"{coverage['total_mutation_runs']:,}", TEAL)
    metric(draw, 618, 190, "PDA / IVR", f"{metrics['paired_discrimination_accuracy']:.0%} / {metrics['invariance_violation_rate']:.0%}", GREEN)
    metric(draw, 891, 190, "严重度相关", f"ρ={metrics['severity_drop_spearman']:.3f}", AMBER)
    full = ablation["strategy_results"]["full_chronofin"]["destructive_detection_rate"]
    pit = ablation["strategy_results"]["point_in_time_exact_citation"]["destructive_detection_rate"]
    exact = ablation["strategy_results"]["exact_citation_only"]["destructive_detection_rate"]
    total_outcomes = ablation["coverage"]["total_strategy_mutation_runs"]
    card(draw, (72, 330, 1208, 620), f"四策略组件消融 · {total_outcomes:,} 条 outcome")
    text_block(draw, (112, 397), f"no audit 0%   →   exact citation {exact:.1%}   →   PIT + citation {pit:.1%}   →   full ChronoFin {full:.0%}", 26, TEXT, 1040, 12)
    causal_metrics = causal["metrics"]
    text_block(draw, (112, 482), f"保存的 Hy3 证据叶答案，经当前门禁离线重绑：CKR={causal_metrics['causal_key_response']:.0f} · locality={causal_metrics['locality']:.0f} · fidelity={causal_metrics['causal_fidelity']:.0f}", 21, MUTED, 1040)
    challenge_summary = challenge["summary"]
    text_block(draw, (112, 548), f"可见回归夹具：{challenge_summary['base_passed']}/{challenge_summary['base_total']} 基础案例 + {challenge_summary['adversarial_passed']}/{challenge_summary['adversarial_total']} 未来泄漏攻击通过；不宣称盲测。", 19, AMBER, 1040)
    frames.append(image)

    image, draw = base_frame(8, "ChronoFin · 让金融答案可被反驳", "结论")
    text_block(draw, (90, 225), "何时可知", 42, AMBER, 300)
    text_block(draw, (460, 225), "依据什么", 42, BLUE, 300)
    text_block(draw, (830, 225), "改一处影响哪里", 42, GREEN, 360)
    draw.line((90, 300, 1180, 300), fill="#2d5866", width=3)
    text_block(draw, (90, 355), "完整源码 · 自定义十维评估 · 失败—修复链 · 腾讯官方财报案例 · 可重复离线验收", 29, TEXT, 1090, 15)
    text_block(draw, (90, 470), "边界：形式化压力集不是人工专家验证；当前回归夹具不是外部盲测；系统不提供投资建议。", 23, MUTED, 1090)
    frames.append(image)

    # Pillow duration uses milliseconds; 8 × 7 seconds = 56 seconds.
    return frames, [7000] * len(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "assets" / "chronofin_demo.gif")
    args = parser.parse_args()
    frames, durations = build_frames()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(json.dumps({
        "output": str(output),
        "frames": len(frames),
        "duration_seconds": sum(durations) / 1000,
        "dimensions": [WIDTH, HEIGHT],
        "bytes": output.stat().st_size,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
