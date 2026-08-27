# Evaluator 组件消融与朴素基线

本实验回答一个窄问题：**在同一批已知正确的合成回答上，逐步加入 citation、时点和完整证明链审计后，哪些受控破坏开始能被检出？** 它不比较金融问答模型能力，也不比较 Hy3 与其他模型。

## 公平比较协议

- 样本来自 `build_synthetic_tasks()`；公司、披露、数值、答案和 oracle 全部是模板生成的 synthetic formal oracle。
- 每个策略接收完全相同的基础答案、chunk registry 和运行时 `DEFAULT_CONTRAST_MUTATIONS`。新增变异会自动进入实验，不在消融代码中硬编码数量。
- 对破坏性变异，只有当该策略的 mutated score 比同任务 clean score 下降超过 `1e-9` 才算检出；对 label-preserving 变异，任何超过该阈值的变化都算 invariance violation。
- 分数只在“同策略、同任务、同变异的前后”配对使用。四个策略的公式和刻度不同，不能横向比较原始分或下降幅度。
- 全程 0 次模型调用、0 次网络调用。实验比较的是审计组件，不是答案生成器。

## 四个策略

| 策略 | 实际检查 | 明确不检查 |
| --- | --- | --- |
| `no_audit_plain_output` | 不检查；恒定返回 100，作为 no-audit negative control | 全部风险 |
| `exact_citation_only` | evidence identity；quote 是否为 registry chunk 的非空精确子串 | claim coverage/支持、时点、数值、实体/期间/单位、图、安全 |
| `point_in_time_exact_citation` | 上述两项；registry `published_at` 与 claim `known_at` 是否越过或错配 cutoff | 数值、claim coverage/支持、实体/期间/单位、图、安全 |
| `full_chronofin` | 完整十维 evaluator 和 hard gates；提供 synthetic expected semantic keys | 不调用 semantic LLM judge；事实得分只来自精确证据片段或规范计算投影，词法重叠仅作诊断 |

`no_audit_plain_output` 不是“弱模型”；它只是展示没有验证层时，格式正确的错误输出不会自动暴露。两个 citation 策略也是 ChronoFin 内部组件的消融，不是独立开发的外部强基线。

## 运行与复现

```bash
PYTHONPATH=src python scripts/run_evaluator_ablation.py
```

完整逐任务结果写入 `results/evaluator_ablation.json`，包括：

- 每个策略的总体 destructive detection rate 与 invariance violation rate；
- 每一种运行时变异的检出率；
- 相邻组件阶梯新增/丢失的成对检出数；
- 每条 `strategy × task × mutation` outcome；
- task、mutation 与策略定义共同计算的 SHA-256 protocol fingerprint。

## 当前全量结果快照

当前运行时 registry 含 36 类破坏性变异与 2 类 label-preserving 变异。72 个基础任务使每个策略运行 2,736 个配对样本，其中破坏 2,592、等价 144；四个策略合计 10,944 个 `strategy × task × mutation` outcome。

| 策略 | 破坏检出率 | 不变性违规率 |
| --- | ---: | ---: |
| `no_audit_plain_output` | 0/2592 = 0.000000 | 0/144 = 0.000000 |
| `exact_citation_only` | 144/2592 = 0.055556 | 0/144 = 0.000000 |
| `point_in_time_exact_citation` | 360/2592 = 0.138889 | 0/144 = 0.000000 |
| `full_chronofin` | 2592/2592 = 1.000000 | 0/144 = 0.000000 |

逐类检出率如下；`—` 表示 label-preserving 类报告的是 invariance violation rate，而非“破坏检出”。

| 变异 | plain | exact citation | point-in-time + exact | full |
| --- | ---: | ---: | ---: | ---: |
| `forged_quote` | 0 | 1 | 1 | 1 |
| `citation_metadata_forgery` | 0 | 1 | 1 | 1 |
| `future_leak` | 0 | 0 | 1 | 1 |
| `known_at_mismatch` | 0 | 0 | 1 | 1 |
| `missing_known_at` | 0 | 0 | 1 | 1 |
| `wrong_entity` | 0 | 0 | 0 | 1 |
| `wrong_period` | 0 | 0 | 0 | 1 |
| `claim_text_wrong_entity` | 0 | 0 | 0 | 1 |
| `claim_text_wrong_period` | 0 | 0 | 0 | 1 |
| `claim_polarity_reversal` | 0 | 0 | 0 | 1 |
| `wrong_query_entity` | 0 | 0 | 0 | 1 |
| `wrong_query_period` | 0 | 0 | 0 | 1 |
| `wrong_query_metric` | 0 | 0 | 0 | 1 |
| `wrong_unit` | 0 | 0 | 0 | 1 |
| `wrong_fact_unit` | 0 | 0 | 0 | 1 |
| `wrong_operand_unit` | 0 | 0 | 0 | 1 |
| `calculation_error` | 0 | 0 | 0 | 1 |
| `claim_text_numeric_error` | 0 | 0 | 0 | 1 |
| `extraneous_claim_number` | 0 | 0 | 0 | 1 |
| `chinese_numeral_error` | 0 | 0 | 0 | 1 |
| `summary_numeric_error` | 0 | 0 | 0 | 1 |
| `summary_unsupported_claim` | 0 | 0 | 0 | 1 |
| `missing_citation` | 0 | 0 | 0 | 1 |
| `prompt_injection` | 0 | 0 | 0 | 1 |
| `caveat_prompt_injection` | 0 | 0 | 0 | 1 |
| `caveat_investment_advice` | 0 | 0 | 0 | 1 |
| `imperative_investment_advice` | 0 | 0 | 0 | 1 |
| `false_caveat_assertion` | 0 | 0 | 0 | 1 |
| `empty_answer` | 0 | 0 | 0 | 1 |
| `affirmative_unknown_claim` | 0 | 0 | 0 | 1 |
| `blanket_refusal` | 0 | 0 | 0 | 1 |
| `incorrect_refusal` | 0 | 0 | 0 | 1 |
| `irrelevant_future_refusal` | 0 | 0 | 0 | 1 |
| `unrelated_negative_refusal` | 0 | 0 | 0 | 1 |
| `cross_clause_negative_refusal` | 0 | 0 | 0 | 1 |
| `available_source_future_refusal` | 0 | 0 | 0 | 1 |
| `claim_order`（IVR） | 0 | 0 | 0 | 0 |
| `format_whitespace`（IVR） | 0 | 0 | 0 | 0 |

增量解释也严格按同 task、同 mutation 配对：

- exact-citation 相对 no-audit 新检出 144 个样本，即 `forged_quote` 与 `citation_metadata_forgery` 两类；
- 加入 point-in-time 后再新检出 216 个样本，即 `future_leak`、`known_at_mismatch`、`missing_known_at` 三类；
- 完整 evaluator 再新检出 2,232 个样本，即其余 31 类；
- 三个阶梯均未丢失前一策略已经检出的样本。

这里的“新增”是描述性配对计数，不能解释为真实数据上的统计因果效应。若 registry 后续增加变异，应重新运行脚本，并以 JSON 中动态生成的 coverage、strategy results 和逐类结果为准。

## 解释边界

本实验只能证明代码在固定形式化变异上的行为。它没有 held-out 样本、人工专家标签或外部系统，不估计真实财报问答准确率、投资正确性或生产可靠性。某类变异被检出不代表 claim 在自然数据上语义正确；未检出也可能只是该消融策略按定义不具备相应组件。结果中的 paired component gain 是描述性计数，不是统计显著性或因果效应估计。
